"""REST search API : normalise et fédère les 5 sources de jurisprudence.

Endpoints servis par token_server.py :
  GET /api/search?q=...&juridiction=...&formation=...&date_from=...&date_to=...&limit=...
  GET /api/decision?source=...&id=...

Sources agrégées : DILA judic (local), HUDOC CEDH (local), EUR-Lex CJUE (local),
ArianeWeb CE (live), Open Data admin ES (live). Les deux dernières sont
appelées en async via asyncio ; les index locaux via sqlite3.
"""
from __future__ import annotations

import asyncio
import re
import sqlite3
from pathlib import Path
from typing import Any

# Pour le hook direct-lookup par numéro CE
# (q injectée via fermeture dans search_federated)

import httpx

from sources import ariane, juriadmin, dila, european

DB_PATH = Path("/opt/justicelibre/dila/judiciaire.db")

# ─── PARSEUR D'OPÉRATEURS ──────────────────────────────────────────

def normalize_query(q: str) -> str:
    """Convertit les opérateurs multi-syntaxe en FTS5/ES canonique (AND/OR/NOT)."""
    if not q:
        return ""
    q = q.strip()

    # Protéger les phrases exactes "..."
    phrases: list[str] = []
    def _protect(m):
        phrases.append(m.group(0))
        return f"\x00{len(phrases)-1}\x00"
    q = re.sub(r'"[^"]*"', _protect, q)

    # Symboles : & → AND, | → OR (espaces optionnels)
    q = re.sub(r"\s*&\s*", " AND ", q)
    q = re.sub(r"\s*\|\s*", " OR ", q)

    # - devant un mot (début ou après espace) = exclusion → NOT mot
    q = re.sub(r"(^|\s)-(\w+\*?)", r"\1NOT \2", q)

    # Tokens composés (14-80854, ECLI:FR:CCASS:2014:CR07114, C-72/24, etc.) :
    # les envelopper en phrase exacte pour que FTS5 les cherche comme
    # séquence adjacente (sinon le "-" = NOT et "14 80854" matche trop large).
    def _quote_compound(m):
        inner = re.sub(r"[-/:]+", " ", m.group(0))
        return f'"{inner}"'
    q = re.sub(r"\b\w+(?:[-/:]\w+)+\b", _quote_compound, q)

    # Mots-clés français
    q = re.sub(r"\bET\b", "AND", q, flags=re.IGNORECASE)
    q = re.sub(r"\bOU\b", "OR", q, flags=re.IGNORECASE)
    q = re.sub(r"\bSAUF\b", "NOT", q, flags=re.IGNORECASE)

    # Normaliser les espaces
    q = re.sub(r"\s+", " ", q).strip()

    # Rétablir les phrases
    for i, p in enumerate(phrases):
        q = q.replace(f"\x00{i}\x00", p)
    return q


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


# ─── RECHERCHE FÉDÉRÉE ─────────────────────────────────────────────

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

    Si `sources_only` est fourni, restreint aux sources listées (intersection
    avec celles impliquées par `juridiction`). Utile pour du streaming
    progressif côté frontend (un appel par source).
    """
    q_norm = normalize_query(q)
    if not q_norm:
        return {"total": 0, "results": [], "per_source": {}}

    sources_to_query = JURI_DISPATCH.get(juridiction, JURI_DISPATCH[""])
    if sources_only:
        sources_to_query = [s for s in sources_to_query if s in sources_only]

    async def _q_ariane(client):
        if "ariane" not in sources_to_query:
            return []
        results = []
        # Si la query est un pur numéro CE (5-7 chiffres), tenter aussi un
        # lookup direct par ID ArianeWeb (ce moteur n'indexe pas les IDs)
        q_raw = q.strip()
        if offset == 0 and re.fullmatch(r"\d{5,7}", q_raw):
            try:
                text = await ariane.fetch_full_text(
                    client, f"/Ariane_Web/AW_DCE/|{q_raw}"
                )
                if text and len(text) > 200:
                    # Extraire un titre court depuis le début du texte
                    first_line = text.split("\n")[0][:120]
                    results.append({
                        "id": f"/Ariane_Web/AW_DCE/|{q_raw}",
                        "source": "ariane",
                        "source_label": SOURCE_LABELS["ariane"],
                        "title": first_line or f"Arrêt CE n° {q_raw}",
                        "juridiction": "Conseil d'État",
                        "date": "",
                        "formation": "",
                        "numero": q_raw,
                        "ecli": "",
                        "extract": text[:400],
                    })
            except Exception as e:
                print(f"[ariane direct lookup err] {e}")
        try:
            r = await ariane.search(client, query=q_norm, limit=limit_per_source, skip=offset)
            results.extend([_norm_ariane(d) for d in r.get("decisions", [])])
        except Exception as e:
            print(f"[ariane err] {e}")
        return results

    ALL_TA = list(juriadmin.TRIBUNAUX_ADMIN.keys())  # 40 TAs (dont outre-mer)
    ALL_CAA = list(juriadmin.COURS_ADMIN_APPEL.keys())  # 9 CAAs

    async def _q_admin(client):
        if "admin" not in sources_to_query:
            return []
        try:
            # Fan-out TA sans lieu → tous les 40
            if juridiction == "ta" and not lieu:
                r = await juriadmin.search_many(
                    client, query=q_norm, juridictions=ALL_TA, limit_per_court=1,
                )
                return [_norm_admin(d) for d in r.get("decisions", [])][:limit_per_source]
            # Fan-out CAA sans lieu → tous les 9
            if juridiction == "caa" and not lieu:
                r = await juriadmin.search_many(
                    client, query=q_norm, juridictions=ALL_CAA,
                    limit_per_court=max(1, limit_per_source // 3),
                )
                return [_norm_admin(d) for d in r.get("decisions", [])][:limit_per_source]
            # Toutes juridictions / admin sans lieu : fan-out CE + 9 CAAs + 40 TAs
            # (50 calls parallèles, chacune avec 1 résultat max)
            if juridiction in ("", "admin") and not lieu:
                fanout = ["CE-CAA"] + ALL_CAA + ALL_TA
                r = await juriadmin.search_many(
                    client, query=q_norm, juridictions=fanout, limit_per_court=1,
                )
                return [_norm_admin(d) for d in r.get("decisions", [])][:limit_per_source]
            code = _admin_juri_code(juridiction, lieu) or "CE"
            r = await juriadmin.search(client, query=q_norm, juridiction=code, limit=limit_per_source)
            return [_norm_admin(d) for d in r.get("decisions", [])]
        except Exception as e:
            print(f"[admin err] {e}")
            return []

    # Les 3 sources locales (SQLite) : appels sync encapsulés en run_in_executor
    def _q_dila_sync():
        if "dila" not in sources_to_query:
            return []
        juri_filter = None
        if juridiction == "cass":
            juri_filter = "cassation"
        elif juridiction == "ca":
            juri_filter = "appel"
        try:
            r = dila.search(query=q_norm, juridiction=juri_filter, limit=limit_per_source, offset=offset)
            return [_norm_dila(d) for d in r.get("decisions", [])]
        except Exception as e:
            print(f"[dila err] {e}")
            return []

    def _q_cedh_sync():
        if "cedh" not in sources_to_query:
            return []
        try:
            r = european.search_cedh(query=q_norm, limit=limit_per_source, offset=offset)
            return [_norm_cedh(d) for d in r.get("decisions", [])]
        except Exception as e:
            print(f"[cedh err] {e}")
            return []

    def _q_cjue_sync():
        if "cjue" not in sources_to_query:
            return []
        try:
            r = european.search_cjue(query=q_norm, limit=limit_per_source, offset=offset)
            return [_norm_cjue(d) for d in r.get("decisions", [])]
        except Exception as e:
            print(f"[cjue err] {e}")
            return []

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
        "query_normalized": q_norm,
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
