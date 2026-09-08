#!/usr/bin/env python3
"""Banc de comparaison contre la RÉFÉRENCE : Judilibre (et Légifrance quand son API répond).

Pourquoi (8 septembre 2026) : un classement faux ne se voit pas à l'œil — le
banc hostile a trouvé un jugement hors sujet en 2ᵉ position, et personne ne
l'aurait remarqué sans lire le texte. Un trou ou un classement faux ne se
détecte que contre une référence EXTÉRIEURE. Ici : pour chaque requête,
les 10 premiers de Judilibre (le moteur officiel de la Cour de cassation)
contre les nôtres, appariés par ECLI (ou numéro + date).

Ne copie rien, mesure. Trois chiffres par requête :
  - recouvrement@10 : combien des 10 premiers de la référence sont dans nos 10 ;
  - rang chez nous du n° 1 de la référence (dans nos 30 premiers, sinon « — ») ;
  - orphelins : nos 3 premiers absents des 50 premiers de la référence
    (candidats « hors sujet », à lire).

Tourne sur la PROD (a besoin des clés PISTE du .env) :
    cd /opt/justicelibre && python3 tests/bench_reference.py [--legifrance] [--site URL]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import httpx

REQUETES = [
    "licenciement sans cause réelle et sérieuse",
    "trouble anormal de voisinage",
    "bail commercial indemnité d'éviction",
    "harcèlement moral",
    "garde à vue nullité",
    "clause de non-concurrence",
    "prescription biennale assurance",
    "vice caché vente immobilière",
    "résiliation judiciaire du contrat de travail",
    "responsabilité du fait des choses",
    "aide juridictionnelle délai de recours",
    "taux effectif global erroné",
    "expulsion trêve hivernale",
    "prestation compensatoire divorce",
    "recel successoral",
    "faute inexcusable de l'employeur",
    "cautionnement disproportionné",
    "droit de rétractation consommateur",
    "abus de confiance détournement",
    "diffamation liberté d'expression",
]


def _env():
    for line in open("/opt/justicelibre/.env"):
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _token() -> str:
    r = httpx.post("https://oauth.piste.gouv.fr/api/oauth/token", data={
        "grant_type": "client_credentials", "client_id": os.environ["PISTE_CLIENT_ID"],
        "client_secret": os.environ["PISTE_CLIENT_SECRET"], "scope": "openid"}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def cle(r: dict) -> str | None:
    """Clé d'appariement : ECLI si présent, sinon numéro normalisé + date."""
    e = (r.get("ecli") or "").strip().upper()
    if e:
        return e
    n = re.sub(r"[.\s/-]", "", str(r.get("numero") or r.get("number") or ""))
    d = (r.get("date") or r.get("decision_date") or "")[:10]
    return f"{n}@{d}" if n and d else None


def judilibre(tok: str, q: str, n: int) -> list[dict]:
    h = {"Authorization": f"Bearer {tok}"}
    r = httpx.get("https://api.piste.gouv.fr/cassation/judilibre/v1.0/search",
                  params={"query": q, "page_size": min(n, 50)}, headers=h, timeout=40)
    r.raise_for_status()
    return r.json().get("results", [])


def legifrance(tok: str, q: str, n: int) -> list[dict] | None:
    h = {"Authorization": f"Bearer {tok}", "accept": "application/json", "Content-Type": "application/json"}
    body = {"fond": "JURI", "recherche": {"champs": [{"typeChamps": "ALL", "criteres": [
        {"typeRecherche": "TOUS_LES_MOTS_DANS_UN_CHAMP", "valeur": q, "operateur": "ET"}], "operateur": "ET"}],
        "filtres": [], "pageNumber": 1, "pageSize": min(n, 100), "operateur": "ET",
        "sort": "PERTINENCE", "typePagination": "DEFAUT"}}
    r = httpx.post("https://api.piste.gouv.fr/dila/legifrance/lf-engine-app/search", json=body, headers=h, timeout=40)
    if r.status_code != 200:
        return None
    out = []
    for res in r.json().get("results", []):
        t = (res.get("titles") or [{}])[0]
        out.append({"id": t.get("id"), "ecli": res.get("ecli") or "", "numero": res.get("num") or "",
                    "date": (res.get("dateSignature") or res.get("date") or "")[:10], "title": t.get("title")})
    return out


def site(base: str, q: str, n: int) -> list[dict]:
    url = f"{base}/api/search?" + urllib.parse.urlencode(
        {"q": q, "sources": "dila", "juridiction": "judic", "limit": n, "expand": 0, "timeout": 30})
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "justicelibre-bench/1.0"}), timeout=90) as r:
        return json.loads(r.read()).get("results", [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="https://justicelibre.org")
    ap.add_argument("--legifrance", action="store_true")
    ap.add_argument("--rapport", default="/tmp/bench_reference.md")
    args = ap.parse_args()
    _env()
    tok = _token()

    lignes = []
    tot_rec = tot_q = 0
    rang1 = []
    orphelins_all = []
    lf_dispo = None
    for q in REQUETES:
        try:
            ref50 = judilibre(tok, q, 50)
        except Exception as e:
            print(f"  ! Judilibre KO sur {q!r} : {e}")
            continue
        ref10 = ref50[:10]
        t0 = time.time()
        try:
            nous30 = site(args.site, q, 30)
        except Exception as e:
            print(f"  ! site KO sur {q!r} : {e}")
            continue
        dt = time.time() - t0
        k_ref10 = [cle(r) for r in ref10]
        k_ref50 = {cle(r) for r in ref50} - {None}
        k_nous30 = [cle(r) for r in nous30]
        k_nous10 = set(k_nous30[:10]) - {None}
        rec = sum(1 for k in k_ref10 if k and k in k_nous10)
        r1 = k_ref10[0] if k_ref10 else None
        rang = (k_nous30.index(r1) + 1) if r1 and r1 in k_nous30 else None
        orph = [(r.get("juridiction"), r.get("numero"), r.get("date")) for r in nous30[:3] if cle(r) not in k_ref50]
        lf = None
        if args.legifrance:
            lf = legifrance(tok, q, 10)
            lf_dispo = lf is not None
        lignes.append((q, rec, rang, orph, dt, len(ref50), lf))
        tot_rec += rec
        tot_q += 1
        if rang:
            rang1.append(rang)
        orphelins_all.extend(orph)
        print(f"{q[:44]:44} recouvrement@10={rec:2}/10  n°1 réf → rang {rang if rang else '—':>3}  orphelins top3={len(orph)}  ({dt:.1f}s)")

    print(f"\nMoyenne recouvrement@10 : {tot_rec / max(1, tot_q):.1f}/10 sur {tot_q} requêtes")
    print(f"n°1 de la référence retrouvé dans nos 30 : {len(rang1)}/{tot_q}, rang médian {sorted(rang1)[len(rang1)//2] if rang1 else '—'}")
    print(f"orphelins (nos top-3 absents du top-50 de la référence) : {len(orphelins_all)} / {3 * tot_q}")
    if args.legifrance:
        print("Légifrance :", "disponible" if lf_dispo else "API en erreur (500) — non comparée")

    with open(args.rapport, "w", encoding="utf-8") as fh:
        fh.write("# Banc de référence — Judilibre vs justicelibre.org (source dila, judiciaire)\n\n")
        fh.write("| requête | recouvrement@10 | rang chez nous du n°1 réf. | orphelins top-3 | temps |\n|---|---|---|---|---|\n")
        for q, rec, rang, orph, dt, nref, lf in lignes:
            o = "; ".join(f"{j} {n} {d}" for j, n, d in orph) or "—"
            fh.write(f"| {q} | {rec}/10 | {rang or '—'} | {o} | {dt:.1f}s |\n")
        fh.write(f"\nMoyenne recouvrement@10 : {tot_rec / max(1, tot_q):.1f}/10 ; n°1 retrouvé {len(rang1)}/{tot_q} ; orphelins {len(orphelins_all)}/{3 * tot_q}\n")
    print(f"rapport : {args.rapport}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
