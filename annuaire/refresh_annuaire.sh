#!/bin/bash
# Régénération mensuelle de l'annuaire, avec garde-fous anti-données-pourries.
# Pipeline complet : sources fraîches → CSV → JSON/HTML → sanity gates → déploiement.
#
# Usage :
#   refresh_annuaire.sh --dry-run   # régénère + vérifie, NE déploie PAS (défaut)
#   refresh_annuaire.sh --deploy    # régénère, vérifie, ET déploie si les gates passent
#
# Variables d'env attendues (défauts = poste de dev) :
#   ANNUAIRE_SRC   répertoire de travail (CSV + dump + web/)   [/home/dahl/annuaire]
#   ANNUAIRE_REPO  clone git justicelibre                       [/home/dahl/justicelibre]
#   PROD_HOST      cible rsync du déploiement                   [root@46.225.190.237]
set -euo pipefail

MODE="${1:---dry-run}"
SRC="${ANNUAIRE_SRC:-/home/dahl/annuaire}"
REPO="${ANNUAIRE_REPO:-/home/dahl/justicelibre}"
PROD_HOST="${PROD_HOST:-root@46.225.190.237}"
WEB="$SRC/web"
export ANNUAIRE_SRC="$SRC" ANNUAIRE_REPO="$REPO"

echo "== [1/5] Rafraîchissement des sources =="
# Dump DILA (services locaux) — ~260 Mo, quotidien.
curl -fSL --retry 3 -o "$SRC/all_latest.tar.bz2" \
  "https://lecomarquage.service-public.gouv.fr/donnees_locales_v4/all_latest.tar.bz2"
tar xjf "$SRC/all_latest.tar.bz2" -C "$SRC" --wildcards '*.json' --transform 's,.*/,,' 2>/dev/null || true
# On garde le nom attendu par le pipeline
NEWEST=$(ls -t "$SRC"/*.json 2>/dev/null | grep -v annuaire_ | head -1 || true)
[ -n "$NEWEST" ] && [ "$NEWEST" != "$SRC/dila_annuaire_local.json" ] && mv "$NEWEST" "$SRC/dila_annuaire_local.json"
rm -f "$SRC/all_latest.tar.bz2"
python3 "$SRC/fetch_api_annuaire.py"      # services centraux (API)
python3 "$SRC/scrape_prada.py" || echo "  (scrape PRADA échoué, on garde l'ancien prada_full.csv)"

echo "== [2/5] Extraction justice (dump → justice_mails.csv) =="
cp -f "$SRC/justice_mails.csv" "$SRC/justice_mails.csv.prev" 2>/dev/null || true
python3 "$SRC/extract_justice_mails.py"

echo "== [3/5] Génération JSON + HTML =="
python3 "$SRC/build_annuaire.py"
python3 "$SRC/build_inedits.py" || echo "  (build_inedits ignoré : source PDF absente)"

echo "== [4/5] Sanity gates (refus de déployer si données pourries) =="
python3 - "$WEB" <<'PY'
import json, sys, csv
from pathlib import Path
web = Path(sys.argv[1])
errs = []
# a) le JSON principal existe, parse, et a un volume plausible
d = json.load(open(web / "annuaire_juridictions.json", encoding="utf-8"))
rows = d.get("rows", [])
if len(rows) < 50_000:
    errs.append(f"annuaire_juridictions.json: seulement {len(rows)} fiches (< 50000, dump tronqué ?)")
# b) aucune fiche sans nom, aucun mail malformé sur un échantillon large
noname = sum(1 for r in rows if not (r.get("nom") or r.get("organisme")))
if noname:
    errs.append(f"{noname} fiches sans nom")
bad_mail = sum(1 for r in rows if r.get("mail") and "@" not in r["mail"])
if bad_mail:
    errs.append(f"{bad_mail} mails sans @")
# c) le CSV justice a bien ses ~1700 lignes
with open(web / "annuaire_juridictions.csv", encoding="utf-8") as f:
    n = sum(1 for _ in f) - 1
if n < 1500:
    errs.append(f"annuaire_juridictions.csv: {n} lignes (< 1500)")
# d) les sous-pages HTML clés existent et ne sont pas vides
for p in ["annuaire/mairies.html", "annuaire/tresoreries.html"]:
    f = web / p
    if not f.exists() or f.stat().st_size < 10_000:
        errs.append(f"{p} absente ou trop petite")
if errs:
    print("ÉCHEC des sanity gates :")
    for e in errs: print("  -", e)
    sys.exit(1)
print(f"  OK : {len(rows)} fiches, {n} juridictions, sous-pages présentes.")
PY

if [ "$MODE" != "--deploy" ]; then
    echo "== [5/5] DRY-RUN : rien n'est déployé. Relancer avec --deploy pour publier. =="
    exit 0
fi

echo "== [5/5] Déploiement vers $PROD_HOST =="
# Copie les artefacts générés dans le clone git, commit, push, puis rsync.
cp "$WEB"/annuaire.html "$REPO/web/"
cp "$WEB"/annuaire/*.html "$REPO/web/annuaire/"
cp "$WEB"/annuaire_*.json "$WEB"/annuaire_*.csv "$REPO/web/data/" 2>/dev/null || true
cp "$WEB"/annuaire_juridictions.json "$REPO/web/data/" 2>/dev/null || true
cd "$REPO"
git add web/ && git commit -q -m "annuaire: régénération mensuelle automatique ($(date +%Y-%m-%d))" || echo "  (rien à committer)"
git push -q origin main || echo "  (push différé)"
rsync -az "$WEB"/annuaire.html "$PROD_HOST:/var/www/justicelibre/"
rsync -az "$WEB"/annuaire/ "$PROD_HOST:/var/www/justicelibre/annuaire/"
rsync -az "$WEB"/annuaire_juridictions.json "$WEB"/annuaire_prada.json "$WEB"/annuaire_meta.json \
          "$WEB"/annuaire_juridictions.csv "$WEB"/annuaire_prada.csv "$PROD_HOST:/var/www/justicelibre/data/"
echo "== Déploiement terminé. =="
