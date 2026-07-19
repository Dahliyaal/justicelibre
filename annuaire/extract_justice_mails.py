#!/usr/bin/env python3
"""Extrait les juridictions/organismes justice du dump DILA local
→ justice_mails.csv (le maillon du pipeline annuaire qui n'était pas scripté).

Entrée  : dila_annuaire_local.json (dump lecomarquage, ~86k services)
Sortie  : justice_mails.csv  (type;nom;mails;tel;site;id)

Types justice retenus = les 16 codes pivot historiques (voir HANDOFF.md).
Déterministe : tri par id, pour des diffs propres d'un mois sur l'autre.
"""
import csv
import json
import os
from pathlib import Path

SRC = Path(os.environ.get("ANNUAIRE_SRC", "/home/dahl/annuaire"))

JUSTICE_TYPES = {
    "tgi", "ti", "cour_appel", "ta", "caa", "prudhommes", "te",
    "tribunal_commerce", "tae", "cdad", "mjd", "spip", "ordre_avocats",
    "vif_tj", "vif_ca", "bav",
}


def all_vals(v, sep=";"):
    """Champs DILA de type liste d'objets {valeur: ...} → toutes les valeurs."""
    if not v:
        return ""
    if isinstance(v, dict):
        v = [v]
    if not isinstance(v, list):
        return str(v).strip()
    vals = []
    for item in v:
        val = (item.get("valeur") or "").strip() if isinstance(item, dict) else str(item).strip()
        if val:
            vals.append(val)
    return sep.join(vals)


def first_val(v):
    """Première valeur seulement (pour le site : un seul lien affiché)."""
    return all_vals(v).split(";")[0]


def main():
    with (SRC / "dila_annuaire_local.json").open(encoding="utf-8") as f:
        services = json.load(f)["service"]

    rows = []
    for s in services:
        pivots = [p.get("type_service_local") for p in (s.get("pivot") or [])]
        jt = next((t for t in pivots if t in JUSTICE_TYPES), None)
        if not jt:
            continue
        rows.append({
            "type": jt,
            "nom": (s.get("nom") or "").strip(),
            "mails": " ; ".join(m.strip() for m in (s.get("adresse_courriel") or []) if m.strip()),
            "tel": all_vals(s.get("telephone")),
            "site": first_val(s.get("site_internet")),
            "id": s.get("id") or "",
        })

    rows.sort(key=lambda r: r["id"])
    out = SRC / "justice_mails.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["type", "nom", "mails", "tel", "site", "id"],
                           delimiter=";")
        w.writeheader()
        w.writerows(rows)
    with_mail = sum(1 for r in rows if r["mails"])
    print(f"{len(rows)} juridictions extraites, {with_mail} avec mail → {out}")


if __name__ == "__main__":
    main()
