#!/usr/bin/env python3
"""Convertit les CSVs annuaire en JSON compact pour la page /annuaire.html.

Génère :
- annuaire_juridictions.json  (les 1711 juridictions, format {rows: [...], types: {...}})
- annuaire_prada.json         (les PRADA sans nom de personne physique par défaut)
- annuaire_meta.json          (dates de dump, counts, stats de complétude)
- annuaire_juridictions.csv   (copie brute — download utilisateur)
- annuaire_prada.csv          (idem)

À exécuter :
- initialement pour le premier déploiement
- chaque mois via cron pour refresh (script deploy_annuaire.sh)
"""
import csv, json, os, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path

SRC = Path("/home/dahl/annuaire")
OUT = SRC / "web"
OUT.mkdir(exist_ok=True)

# Mapping type-code DILA → label humain (les 16 types justice qu'on a)
TYPE_LABELS = {
    "tgi":               "Tribunal judiciaire",
    "ti":                "Tribunal de proximité",
    "cour_appel":        "Cour d'appel",
    "ta":                "Tribunal administratif",
    "caa":               "Cour administrative d'appel",
    "prudhommes":        "Conseil de prud'hommes",
    "te":                "Tribunal pour enfants",
    "tribunal_commerce": "Tribunal de commerce",
    "tae":               "Tribunal des activités économiques",
    "cdad":              "Conseil dép. d'accès au droit",
    "mjd":               "Maison de justice et du droit",
    "spip":              "SPIP (insertion & probation)",
    "ordre_avocats":     "Ordre des avocats",
    "vif_tj":            "Pôle violences intra-familiales (TJ)",
    "vif_ca":            "Pôle violences intra-familiales (CA)",
    "bav":               "Bureau d'aide aux victimes",
}

# ─── Juridictions ────────────────────────────────────────────────
juri_rows = []
stats = {}  # {type: {total, with_mail}}
with (SRC / "justice_mails.csv").open(encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter=";"):
        t = r["type"]
        has_mail = bool(r["mails"].strip())
        stats.setdefault(t, {"total": 0, "with_mail": 0})
        stats[t]["total"] += 1
        if has_mail:
            stats[t]["with_mail"] += 1
        juri_rows.append({
            "id":   r["id"],
            "type": t,
            "nom":  r["nom"],
            "mails": [m.strip() for m in r["mails"].split(";") if m.strip()] if r["mails"] else [],
            "tel":  r["tel"] or "",
            "site": r["site"] or "",
        })

# Trier : d'abord les types "phares" (TJ, CA, CAA, TA, Cass), puis alpha
TYPE_ORDER = ["tgi","ti","cour_appel","ta","caa","tribunal_commerce","prudhommes","te","spip","cdad","mjd","ordre_avocats","tae","vif_tj","vif_ca","bav"]
type_rank = {t: i for i, t in enumerate(TYPE_ORDER)}
juri_rows.sort(key=lambda r: (type_rank.get(r["type"], 99), r["nom"]))

(OUT / "annuaire_juridictions.json").write_text(
    json.dumps({
        "type_labels": TYPE_LABELS,
        "rows": juri_rows,
    }, ensure_ascii=False, separators=(",", ":")),
    encoding="utf-8",
)

# ─── PRADA (sans nom par défaut, colonne 'prada' omise) ────────────
INCLUDE_NAMES = False  # flip à True pour publier les noms de personnes physiques
prada_rows = []
prada_with_mail = 0
with (SRC / "prada_full.csv").open(encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter=";"):
        row = {
            "organisme": r["organisme"],
            "courriel":  r["courriel"] or "",
            "adresse":   r["adresse"] or "",
        }
        if INCLUDE_NAMES:
            row["prada"] = r["prada"] or ""
        if r["courriel"].strip():
            prada_with_mail += 1
        prada_rows.append(row)

prada_rows.sort(key=lambda r: r["organisme"].lower())
(OUT / "annuaire_prada.json").write_text(
    json.dumps({
        "rows": prada_rows,
        "includes_names": INCLUDE_NAMES,
    }, ensure_ascii=False, separators=(",", ":")),
    encoding="utf-8",
)

# ─── Meta (dates + stats globales) ─────────────────────────────────
def stat_mtime_iso(p):
    return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")

meta = {
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "sources": {
        "dila_dump": {
            "url": "https://lecomarquage.service-public.gouv.fr/donnees_locales_v4/all_latest.tar.bz2",
            "downloaded": stat_mtime_iso(SRC / "dila_annuaire_local.json") if (SRC / "dila_annuaire_local.json").exists() else None,
            "provider": "DILA (Premier ministre)",
            "note": "Ne contient QUE les services locaux. Les services nationaux (Cour de cassation, SG ministère de la Justice, etc.) sont dans l'API distincte.",
        },
        "api_lannuaire": {
            "url": "https://api-lannuaire.service-public.fr/api/explore/v2.1/catalog/datasets/api-lannuaire-administration/records",
            "provider": "DILA (Premier ministre)",
            "note": "API Opendatasoft. Contient les services nationaux absents du dump téléchargeable.",
        },
        "cada_prada": {
            "url": "https://www.cada.fr/particulier/personnes-responsables-resultatss",
            "downloaded": stat_mtime_iso(SRC / "prada_full.csv"),
            "provider": "CADA (Commission d'accès aux documents administratifs)",
            "note": "Scrapé depuis le formulaire web (la CADA ne publie pas d'export). 250 pages, 9 résultats/page.",
        },
    },
    "counts": {
        "juridictions_total": len(juri_rows),
        "juridictions_with_mail": sum(1 for r in juri_rows if r["mails"]),
        "prada_total": len(prada_rows),
        "prada_with_mail": prada_with_mail,
    },
    "coverage_by_type": {
        t: {
            "label": TYPE_LABELS.get(t, t),
            "total": s["total"],
            "with_mail": s["with_mail"],
            "rate": round(s["with_mail"] / s["total"] * 100, 1),
        }
        for t, s in stats.items()
    },
    "known_gaps": [
        {"nom": "Cour de cassation", "portee": "nationale", "mail_publie": False, "source": "api-lannuaire"},
        {"nom": "Greffe de la Cour de cassation", "portee": "nationale", "mail_publie": False, "source": "api-lannuaire"},
        {"nom": "Secrétariat général du ministère de la Justice", "portee": "nationale", "mail_publie": False, "source": "api-lannuaire",
         "note": "L'entité qui détient l'annuaire interne des greffes n'a elle-même aucune adresse publiée."},
    ],
    "known_mails_national": [
        {"nom": "Première présidence de la Cour de cassation", "mail": "sg.pp.courdecassation@justice.fr"},
        {"nom": "Parquet général de la Cour de cassation", "mail": "sec.pg.courdecassation@justice.fr"},
        {"nom": "PRADA — Ministère de la Justice", "mail": "cada.sdajgc-sem-sg@justice.gouv.fr"},
        {"nom": "PRADA — Conseil d'État", "mail": "SG-Secretariat@conseil-etat.fr"},
        {"nom": "PRADA — Ministère de l'Intérieur", "mail": "prada@interieur.gouv.fr"},
        {"nom": "PRADA — Premier ministre (SGG)", "mail": "prada.spm@sgg.pm.gouv.fr"},
    ],
}
(OUT / "annuaire_meta.json").write_text(
    json.dumps(meta, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

# ─── Copie brute des CSVs pour download utilisateur ────────────────
shutil.copy(SRC / "justice_mails.csv", OUT / "annuaire_juridictions.csv")
shutil.copy(SRC / "prada_full.csv",    OUT / "annuaire_prada.csv")

# ─── Bilan ─────────────────────────────────────────────────────────
print(f"[annuaire] {len(juri_rows)} juridictions, {sum(1 for r in juri_rows if r['mails'])} avec mail")
print(f"[annuaire] {len(prada_rows)} PRADA, {prada_with_mail} avec mail (noms {'inclus' if INCLUDE_NAMES else 'masqués'})")
print(f"[annuaire] fichiers écrits dans {OUT}/")
for p in sorted(OUT.iterdir()):
    print(f"    {p.name:35} {p.stat().st_size:>10} b")
