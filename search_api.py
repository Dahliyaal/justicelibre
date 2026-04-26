"""REST search API : fédère 5 sources de jurisprudence avec dispatch
intent-aware.

Architecture en 3 couches :
  1. Détection d'intent (`query_intent.detect_intent`) — comprend
     ce que l'user cherche (n° pourvoi, ECLI, ID interne, FTS, etc.)
  2. Routage par capabilités (`query_intent.sources_for_intent`) —
     décide quelles sources sont pertinentes pour cet intent
  3. Dispatch par source — chaque source a sa stratégie selon l'intent
     (lookup direct ID > recherche par champ > FTS5 fallback)

Endpoints servis par token_server.py :
  GET /api/search?q=...&juridiction=...&lieu=...&limit=...&offset=...&sources=...
  GET /api/decision?source=...&id=...
"""
from __future__ import annotations

import asyncio
import re
import sqlite3
from pathlib import Path
from typing import Any

import httpx

from sources import ariane, juriadmin, dila, european
from query_intent import (
    QueryIntent, detect_intent, normalize_fts_query, sources_for_intent,
    SOURCE_CAPABILITIES,
)

DB_PATH = Path("/opt/justicelibre/dila/judiciaire.db")

# ─── ALIAS LEGACY ──────────────────────────────────────────────────
# Le vrai normalizer vit désormais dans `query_intent.normalize_fts_query`.
# On garde l'alias pour ne casser aucun ancien import.

def normalize_query(q: str) -> str:
    return normalize_fts_query(q)


def _clean_date(d: str) -> str:
    """Nettoie une date. Rejette les valeurs aberrantes (ex: 0201-02-24)."""
    if not d or not isinstance(d, str):
        return ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", d.strip())
    if not m:
        return ""
    year = int(m.group(1))
    if year < 1800 or year > 2099:
        return ""
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


# ─── NORMALIZER ────────────────────────────────────────────────────

SOURCE_LABELS = {
    "dila":   "JUDICIAIRE",
    "ariane": "CE",
    "admin":  "ADMIN",
    "cedh":   "CEDH",
    "cjue":   "CJUE",
}

_JURI_LABELS = {
    "cc":   "Cour de cassation",
    "ca":   "Cour d'appel",
    "cec":  "Conseil d'État",
    "constit": "Conseil constitutionnel",
}
def _norm_dila(raw: dict) -> dict:
    juri_raw = raw.get("juridiction", "") or ""
    juri = _JURI_LABELS.get(juri_raw.lower(), juri_raw)
    return {
        "id": raw["id"],
        "source": "dila",
        "source_label": SOURCE_LABELS["dila"],
        "title": raw.get("titre") or f"{juri} — n° {raw.get('numero', '—')}",
        "juridiction": juri,
        "date": _clean_date(raw.get("date", "")),
        "formation": raw.get("formation", ""),
        "numero": raw.get("numero", ""),
        "ecli": raw.get("ecli", ""),
        "extract": raw.get("snippet", "") or "",
    }

def _norm_ariane(raw: dict) -> dict:
    raw_title = (raw.get("title") or "").strip()
    extracts = raw.get("extracts", "") or ""
    # ArianeWeb met "Conseil d'État" comme titre pour tout — prendre la 1re
    # phrase de l'extrait pour avoir un titre parlant.
    if raw_title in ("Conseil d'État", "", "Conseil d'Etat"):
        first_chunk = extracts.split(";")[0].strip().rstrip(".,;")
        if first_chunk and len(first_chunk) > 5:
            raw_title = first_chunk[:140]
        else:
            raw_title = "Arrêt du Conseil d'État"
    return {
        "id": raw.get("id") or "",
        "source": "ariane",
        "source_label": SOURCE_LABELS["ariane"],
        "title": raw_title,
        "juridiction": "Conseil d'État",
        "date": "",
        "formation": "",
        "numero": "",
        "ecli": "",
        "extract": extracts,
        "relevance": raw.get("relevance"),
    }

def _norm_admin(raw: dict) -> dict:
    return {
        "id": raw.get("id") or "",
        "source": "admin",
        "source_label": SOURCE_LABELS["admin"],
        "title": f"{raw.get('juridiction_name', '')} — n° {raw.get('numero_dossier', '—')}",
        "juridiction": raw.get("juridiction_name", ""),
        "date": _clean_date(raw.get("date_lecture", "")),
        "formation": raw.get("formation", ""),
        "numero": raw.get("numero_dossier", ""),
        "ecli": raw.get("ecli") or "",
        "extract": "",
    }

def _norm_jade_bulk(raw: dict) -> dict:
    """Normalise un hit JADE bulk (CETATEXT) au format de réponse search."""
    juri = raw.get("juridiction", "")
    numero = raw.get("numero", "")
    return {
        "id": raw.get("id") or "",
        "source": "admin",
        "source_label": SOURCE_LABELS["admin"],
        "title": raw.get("titre") or (f"{juri} — n° {numero}" if numero else juri),
        "juridiction": juri,
        "date": _clean_date(raw.get("date", "")),
        "formation": raw.get("formation", ""),
        "numero": numero,
        "ecli": raw.get("ecli") or "",
        "extract": "",
    }

def _norm_cedh(raw: dict) -> dict:
    return {
        "id": raw["id"],
        "source": "cedh",
        "source_label": SOURCE_LABELS["cedh"],
        "title": raw.get("docname", "").strip(),
        "juridiction": "Cour EDH",
        "date": _clean_date(raw.get("date", "")),
        "formation": raw.get("doctype", ""),
        "numero": "",
        "ecli": raw.get("ecli", ""),
        "extract": raw.get("snippet", "") or "",
        "article": raw.get("article", ""),
    }

def _norm_cjue(raw: dict) -> dict:
    celex = raw.get("celex") or raw.get("id")
    title = (raw.get("title") or "").strip()
    if not title:
        title = f"Arrêt CJUE — CELEX {celex}"
    return {
        "id": celex,
        "source": "cjue",
        "source_label": SOURCE_LABELS["cjue"],
        "title": title,
        "juridiction": "CJUE",
        "date": _clean_date(raw.get("date", "")),
        "formation": raw.get("type", ""),
        "numero": celex or "",
        "ecli": raw.get("ecli", ""),
        "extract": raw.get("snippet", "") or "",
    }


# ─── DISPATCH : décider quelles sources interroger selon la juridiction ────

# Valeurs du filtre "fine" juridiction → sources à interroger
JURI_DISPATCH = {
    "":        ["dila", "ariane", "admin", "cedh", "cjue"],  # toutes
    "admin":   ["ariane", "admin"],
    "ce":      ["ariane", "admin"],       # CE est dans les deux
    "caa":     ["admin"],
    "ta":      ["admin"],
    "judic":   ["dila"],
    "cass":    ["dila"],
    "ca":      ["dila"],
    "constit": ["dila"],
    "europ":   ["cedh", "cjue"],
    "cedh":    ["cedh"],
    "cjue":    ["cjue"],
}

def _admin_juri_code(juri: str, lieu: str = "") -> str | None:
    """Traduit le filtre UI en code d'API admin ES."""
    if juri == "ce":
        return "CE"
    if juri == "caa":
        return lieu if lieu.startswith("CAA") else None  # besoin code précis
    if juri == "ta":
        return lieu if lieu.startswith("TA") else None
    if juri in ("", "admin"):
        return None  # on interroge CE + fanout si besoin
    return None


# ─── DISPATCH PAR SOURCE × INTENT ──────────────────────────────────
# Chaque dispatcher prend (intent, contexte) et retourne une liste de
# résultats normalisés. Stratégie : direct lookup si l'intent matche
# une capability spécifique, sinon FTS comme fallback.

ALL_TA = list(juriadmin.TRIBUNAUX_ADMIN.keys())   # 40 TAs (dont outre-mer)
ALL_CAA = list(juriadmin.COURS_ADMIN_APPEL.keys())  # 9 CAAs


async def _dispatch_ariane(
    client, intent: QueryIntent, limit: int, offset: int,
) -> list[dict]:
    """ArianeWeb dispatch.

    IMPORTANT : pour un intent `ariane_id`, on fait LES DEUX :
      - direct ID lookup via plugin (peut renvoyer la décision dont
        l'ID INTERNE Ariane = le numéro tapé — souvent pas la bonne)
      - search Sinequa avec le numéro comme texte (peut trouver la
        décision dont le N° de dossier est ce numéro, citée dans le
        texte — souvent la bonne)

    On présente les deux. La direct lookup est marquée comme telle.
    """
    out = []
    seen = set()

    # 1) Lookup direct par ID interne ArianeWeb (5-7 chiffres)
    if intent.kind == "ariane_id" and offset == 0:
        try:
            text = await ariane.fetch_full_text(
                client, f"/Ariane_Web/AW_DCE/|{intent.value}"
            )
            if text and len(text) > 200:
                first_line = text.split("\n")[0][:120]
                aid = f"/Ariane_Web/AW_DCE/|{intent.value}"
                out.append({
                    "id": aid,
                    "source": "ariane",
                    "source_label": SOURCE_LABELS["ariane"],
                    "title": (first_line or f"Arrêt CE — index ArianeWeb {intent.value}"),
                    "juridiction": "Conseil d'État (lookup ID interne ArianeWeb)",
                    "date": "",
                    "formation": "",
                    "numero": intent.value,
                    "ecli": "",
                    "extract": "[Décision dont l'index interne ArianeWeb = " + intent.value + "]. Si tu cherches par n° de DOSSIER CE, voir aussi les autres résultats. " + text[:300],
                })
                seen.add(aid)
        except Exception as e:
            print(f"[ariane id-lookup err] {e}")

    # 2) Search Sinequa : TOUJOURS, même pour ariane_id (le numéro tapé
    #    peut être un n° de dossier, qu'on retrouve dans le texte indexé)
    try:
        r = await ariane.search(client, query=intent.fts_query, limit=limit, skip=offset)
        for d in r.get("decisions", []):
            if d.get("id") not in seen:
                out.append(_norm_ariane(d))
                seen.add(d.get("id"))
    except Exception as e:
        print(f"[ariane fts err] {e}")
    return out


async def _dispatch_admin(
    client, intent: QueryIntent, juridiction: str, lieu: str,
    limit: int, offset: int,
) -> list[dict]:
    out = []
    # 1) Si l'intent est dce_id : fetch_decision direct
    if intent.kind == "dce_id":
        try:
            r = await juriadmin.get_decision(client, decision_id=intent.value)
            if r:
                out.append({**_norm_admin(r), "extract": ""})
                return out
        except Exception as e:
            print(f"[admin dce_id err] {e}")
    # 1bis) Si l'intent est dossier_admin (TA Paris 21XXXXX ou CAA codifié
    # XXNCXXXXX, XXDAXXXXX, XXPAXXXXX…) → lookup SQL exact dans JADE bulk.
    # JADE couvre les anciens numéros que l'API live opendata (post-2022) rate.
    if intent.kind == "dossier_admin":
        try:
            from sources import warehouse as wh
            bulk_hits = await wh.lookup_by_numero("jade", intent.value)
            if bulk_hits:
                out.extend([_norm_jade_bulk(h) for h in bulk_hits[:limit]])
                return out
        except Exception as e:
            print(f"[admin jade lookup err] {e}")
    # 2) Routage du code juridiction selon contexte (fan-out vs single)
    try:
        if juridiction == "ta" and not lieu:
            r = await juriadmin.search_many(
                client, query=intent.fts_query, juridictions=ALL_TA, limit_per_court=1,
            )
            out.extend([_norm_admin(d) for d in r.get("decisions", [])][:limit])
        elif juridiction == "caa" and not lieu:
            r = await juriadmin.search_many(
                client, query=intent.fts_query, juridictions=ALL_CAA,
                limit_per_court=max(1, limit // 3),
            )
            out.extend([_norm_admin(d) for d in r.get("decisions", [])][:limit])
        elif juridiction in ("", "admin") and not lieu:
            fanout = ["CE-CAA"] + ALL_CAA + ALL_TA
            r = await juriadmin.search_many(
                client, query=intent.fts_query, juridictions=fanout, limit_per_court=1,
            )
            out.extend([_norm_admin(d) for d in r.get("decisions", [])][:limit])
        else:
            code = _admin_juri_code(juridiction, lieu) or "CE"
            r = await juriadmin.search(
                client, query=intent.fts_query, juridiction=code, limit=limit,
            )
            out.extend([_norm_admin(d) for d in r.get("decisions", [])])
    except Exception as e:
        print(f"[admin fts err] {e}")
    return out


def _dispatch_dila_sync(
    intent: QueryIntent, juridiction: str, limit: int, offset: int,
) -> list[dict]:
    juri_filter = None
    if juridiction == "cass":
        juri_filter = "cassation"
    elif juridiction == "ca":
        juri_filter = "appel"
    out = []
    seen = set()
    try:
        # 1) Lookups directs par champ (numero, ecli, id) — bypass FTS5
        if intent.kind == "juritext":
            row = dila.get_decision(intent.value)
            if row:
                out.append({**_norm_dila(row), "extract": ""})
                seen.add(row["id"])
        elif intent.kind == "ecli":
            for hit in dila.lookup_by_field("ecli", intent.value, limit=5):
                out.append(_norm_dila(hit))
                seen.add(hit["id"])
        elif intent.kind == "pourvoi":
            for hit in dila.lookup_by_field("numero", intent.value, limit=5):
                out.append(_norm_dila(hit))
                seen.add(hit["id"])
        elif intent.kind == "rg":
            # RG = numero pour les Cours d'appel
            for hit in dila.lookup_by_field("numero", intent.value, limit=5):
                out.append(_norm_dila(hit))
                seen.add(hit["id"])
        # 2) FTS5 toujours en complément (sauf si on a déjà un hit unique)
        if not out or intent.kind in ("fts", "phrase"):
            r = dila.search(
                query=intent.fts_query, juridiction=juri_filter,
                limit=limit, offset=offset,
            )
            for d in r.get("decisions", []):
                if d["id"] not in seen:
                    out.append(_norm_dila(d))
                    seen.add(d["id"])
    except Exception as e:
        print(f"[dila err] {e}")
    return out


def _dispatch_cedh_sync(
    intent: QueryIntent, limit: int, offset: int,
) -> list[dict]:
    out = []
    seen = set()
    try:
        if intent.kind == "itemid_hudoc":
            row = european.get_cedh(intent.value)
            if row:
                out.append({**_norm_cedh(row), "extract": ""})
                seen.add(row["id"])
        if not out or intent.kind in ("fts", "phrase"):
            r = european.search_cedh(query=intent.fts_query, limit=limit, offset=offset)
            for d in r.get("decisions", []):
                if d["id"] not in seen:
                    out.append(_norm_cedh(d))
                    seen.add(d["id"])
    except Exception as e:
        print(f"[cedh err] {e}")
    return out


def _dispatch_cjue_sync(
    intent: QueryIntent, limit: int, offset: int,
) -> list[dict]:
    out = []
    seen = set()
    try:
        if intent.kind == "celex":
            row = european.get_cjue(intent.value)
            if row:
                out.append({**_norm_cjue(row), "extract": ""})
                seen.add(row["id"])
        if not out or intent.kind in ("fts", "phrase"):
            r = european.search_cjue(query=intent.fts_query, limit=limit, offset=offset)
            for d in r.get("decisions", []):
                if d["id"] not in seen:
                    out.append(_norm_cjue(d))
                    seen.add(d["id"])
    except Exception as e:
        print(f"[cjue err] {e}")
    return out


# ─── RECHERCHE FÉDÉRÉE (orchestrateur) ─────────────────────────────

async def search_federated(
    q: str,
    juridiction: str = "",
    lieu: str = "",
    limit: int = 20,
    limit_per_source: int = 10,
    offset: int = 0,
    sources_only: list[str] | None = None,
    timeout_s: float = 12.0,
) -> dict[str, Any]:
    """Interroge en parallèle les sources pertinentes, fusionne et trie.

    1. Détecte l'intent de la query via `detect_intent(q)`
    2. Croise les sources autorisées (par juridiction filter + sources_only)
       avec celles capables de traiter cet intent
    3. Dispatch chaque source avec sa stratégie spécifique à l'intent
    4. Fusionne, trie, retourne
    """
    intent = detect_intent(q)
    if intent.kind == "empty":
        return {"total": 0, "results": [], "per_source": {}}

    # Sources autorisées par le filtre juridiction
    juri_sources = JURI_DISPATCH.get(juridiction, JURI_DISPATCH[""])
    if sources_only:
        juri_sources = [s for s in juri_sources if s in sources_only]
    # Sources capables de traiter cet intent (intersection)
    sources_to_query = sources_for_intent(intent, juri_sources)

    async def _q_ariane(client):
        if "ariane" not in sources_to_query:
            return []
        return await _dispatch_ariane(client, intent, limit_per_source, offset)

    async def _q_admin(client):
        if "admin" not in sources_to_query:
            return []
        return await _dispatch_admin(
            client, intent, juridiction, lieu, limit_per_source, offset,
        )

    def _q_dila_sync():
        if "dila" not in sources_to_query:
            return []
        return _dispatch_dila_sync(intent, juridiction, limit_per_source, offset)

    def _q_cedh_sync():
        if "cedh" not in sources_to_query:
            return []
        return _dispatch_cedh_sync(intent, limit_per_source, offset)

    def _q_cjue_sync():
        if "cjue" not in sources_to_query:
            return []
        return _dispatch_cjue_sync(intent, limit_per_source, offset)

    loop = asyncio.get_event_loop()
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15.0, connect=5.0),
        headers={"User-Agent": "justicelibre/1.0 (+https://justicelibre.org)"},
    ) as client:
        # Timeouts séparés. Sentinel pour distinguer 0 résultat légitime vs timeout
        timed_out = set()
        async def _safe(coro, timeout, label):
            try:
                return await asyncio.wait_for(coro, timeout=timeout)
            except asyncio.TimeoutError:
                print(f"[{label} timeout {timeout}s]")
                timed_out.add(label)
                return []
            except Exception as e:
                print(f"[{label} err]: {e}")
                timed_out.add(label)
                return []

        ariane_task = _safe(_q_ariane(client), timeout_s, "ariane")
        admin_task  = _safe(_q_admin(client), timeout_s, "admin")
        dila_task   = _safe(loop.run_in_executor(None, _q_dila_sync), max(5, timeout_s / 2), "dila")
        cedh_task   = _safe(loop.run_in_executor(None, _q_cedh_sync), max(5, timeout_s / 2), "cedh")
        cjue_task   = _safe(loop.run_in_executor(None, _q_cjue_sync), max(5, timeout_s / 2), "cjue")
        ariane_r, admin_r, dila_r, cedh_r, cjue_r = await asyncio.gather(
            ariane_task, admin_task, dila_task, cedh_task, cjue_task,
        )

    per_source = {
        "ariane": len(ariane_r), "admin": len(admin_r),
        "dila": len(dila_r), "cedh": len(cedh_r), "cjue": len(cjue_r),
    }
    # Sources qui ont timeout ou erreur (DISTINCT des sources qui ont juste rien trouvé)
    slow_sources = [s for s in sources_to_query if s in timed_out]

    # Merge, tri : priorité Sinequa score si dispo, sinon date desc
    merged = [*ariane_r, *admin_r, *dila_r, *cedh_r, *cjue_r]
    def _sort_key(r):
        rel = r.get("relevance")
        if rel is not None:
            return (0, -float(rel), r.get("date", ""))
        return (1, r.get("date", "") or "0000-00-00",)
    merged.sort(key=_sort_key, reverse=False)
    # Invert date desc for items without relevance
    with_rel = [r for r in merged if r.get("relevance") is not None]
    without_rel = [r for r in merged if r.get("relevance") is None]
    without_rel.sort(key=lambda r: r.get("date", ""), reverse=True)
    final = [*with_rel, *without_rel][:limit]

    return {
        "query_normalized": intent.fts_query,
        "intent": intent.kind,
        "total": len(merged),
        "per_source": per_source,
        "sources_queried": sources_to_query,
        "sources_no_result": slow_sources,
        "results": final,
    }


# ─── RÉCUPÉRATION DU TEXTE INTÉGRAL ────────────────────────────────

async def fetch_decision(source: str, decision_id: str) -> dict[str, Any] | None:
    if source == "dila":
        r = dila.get_decision(decision_id)
        if not r:
            return None
        return {
            **_norm_dila(r),
            "full_text": r.get("full_text", ""),
        }
    if source == "cedh":
        r = european.get_cedh(decision_id)
        if not r:
            return None
        return {
            **_norm_cedh(r),
            "full_text": r.get("full_text", ""),
        }
    if source == "cjue":
        r = european.get_cjue(decision_id)
        if not r:
            return None
        return {
            **_norm_cjue(r),
            "full_text": r.get("full_text", ""),
        }
    if source == "admin":
        # Cas 1 : ID JADE bulk (CETATEXT*) → warehouse direct
        # Le live API juriadmin n'a pas les anciens dossiers (avant juin 2022).
        if decision_id.upper().startswith("CETATEXT"):
            try:
                from sources import warehouse as wh
                r = await wh.get_decision_remote("jade", decision_id)
                if not r:
                    return None
                return {
                    **_norm_jade_bulk(r),
                    "full_text": r.get("texte", "") or "",
                    "text_segments": [],
                }
            except Exception as e:
                return {"error": str(e)}
        # Cas 2 : ID live opendata (DCE_*, DTA_*, DCAA_*) → juriadmin
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                r = await juriadmin.get_decision(client, decision_id=decision_id)
                if not r:
                    return None
                return {
                    **_norm_admin(r),
                    "full_text": r.get("full_text", ""),
                    "text_segments": r.get("text_segments", []),
                }
            except Exception as e:
                return {"error": str(e)}
    if source == "ariane":
        async with httpx.AsyncClient(timeout=60.0, headers={
            "User-Agent": "justicelibre/1.0 (+https://justicelibre.org)",
        }) as client:
            try:
                text = await ariane.fetch_full_text(client, decision_id)
                if not text:
                    return {"error": "Texte intégral indisponible pour cette décision ArianeWeb."}
                return {
                    "id": decision_id,
                    "source": "ariane",
                    "source_label": "CE",
                    "title": "Décision du Conseil d'État",
                    "juridiction": "Conseil d'État",
                    "date": "",
                    "formation": "",
                    "numero": "",
                    "ecli": "",
                    "full_text": text,
                }
            except Exception as e:
                return {"error": f"Erreur ArianeWeb : {e}"}
    return {"error": f"Source inconnue : {source!r}"}
