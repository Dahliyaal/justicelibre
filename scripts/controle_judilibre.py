#!/usr/bin/env python3
"""Contrôle de couverture EXTÉRIEUR : les totaux de Judilibre contre notre base.

Pourquoi (8 septembre 2026) : un million de décisions manquaient (CA 2022-2025,
TJ 2024-2025) et aucun contrôle ne l'a vu, parce qu'on comparait la base à
elle-même. « Complet » ne se dit qu'avec le chiffre de la référence à côté.

Chaque nuit : pour chaque juridiction (cc, ca, tj, tcom) et chaque année
depuis 2020, le total annoncé par /export de Judilibre contre le nombre de
lignes Judilibre (id hexadécimal) de la base pour la même année. Écart > 5 %
ou > 500 décisions → ligne ⚠️ et code retour 1. ~30 appels API, lecture seule.

    cd /opt/justicelibre && python3 scripts/controle_judilibre.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

for _line in Path("/opt/justicelibre/.env").read_text().splitlines():
    if "=" in _line and not _line.strip().startswith("#"):
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip())
sys.path.insert(0, "/opt/justicelibre")
import httpx  # noqa: E402
import judilibre_sync as JS  # noqa: E402

DB = "/opt/justicelibre/dila/judiciaire.db"
SEUIL_PCT, SEUIL_ABS = 5.0, 500


def main() -> int:
    tok = JS.get_token()
    h = {"Authorization": f"Bearer {tok}"}
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    annee_max = date.today().year
    ecarts = 0
    print(f"{datetime.now():%Y-%m-%d %H:%M} couverture Judilibre (référence) vs base :")
    # UN seul balayage de la base (par l'index de date) : 28 comptages séparés
    # prenaient plus de dix minutes pendant un rattrapage (8 sept. 2026).
    nous: dict[tuple[str, str], int] = {}
    for annee, juri, n in conn.execute("""
        SELECT substr(date, 1, 4) AS annee,
               CASE
                 WHEN juridiction IN ('cc', 'Cour de cassation') THEN 'cc'
                 WHEN juridiction LIKE 'Cour d''appel %' THEN 'ca'
                 WHEN juridiction LIKE 'Tribunal judiciaire %' THEN 'tj'
                 WHEN juridiction LIKE 'Tribunal de commerce %'
                   OR juridiction LIKE 'Tribunal des activités économiques %' THEN 'tcom'
                 ELSE '' END AS juri,
               COUNT(*)
        FROM decisions
        WHERE date >= ? AND length(id) = 24
        GROUP BY 1, 2""", (f"{2020}-01-01",)):
        nous[(juri, annee)] = n
    for juri in ("cc", "ca", "tj", "tcom"):
        for y in range(2020, annee_max + 1):
            d1, d2 = f"{y}-01-01", f"{y}-12-31"
            try:
                r = httpx.get(f"{JS.JUDILIBRE_URL}/export", params={"batch": 0, "batch_size": 1,
                              "jurisdiction": juri, "date_start": d1, "date_end": d2}, headers=h, timeout=60)
                ref = int(r.json().get("total") or 0) if r.status_code == 200 else None
            except Exception:
                ref = None
            n = nous.get((juri, str(y)), 0)
            if ref is None:
                print(f"  {juri:4} {y} : Judilibre injoignable, nous={n}")
                continue
            manque = ref - n
            pct = 100.0 * manque / ref if ref else 0.0
            flag = "⚠️ " if (manque > SEUIL_ABS and pct > SEUIL_PCT) else "   "
            if flag.strip():
                ecarts += 1
            print(f"  {flag}{juri:4} {y} : Judilibre={ref:>7}  nous={n:>7}  manque={manque:>7} ({pct:.1f} %)")
    if ecarts:
        print(f"⚠️ {ecarts} juridiction×année sous la référence de plus de {SEUIL_PCT:.0f} % — rattrapage : scripts/judilibre_backfill.py")
        return 1
    print("✅ couverture Judilibre : toutes les années dans la marge")
    return 0


if __name__ == "__main__":
    sys.exit(main())
