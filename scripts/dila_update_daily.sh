#!/bin/bash
# Daily DILA delta updater — pulls the missing incremental tarballs for each
# fond and runs parse_dila_bulk.py to merge into existing SQLite DBs.
#
# Install : cron 0 4 * * *  /opt/justicelibre/scripts/dila_update_daily.sh
#
# DILA publie à des heures VARIABLES chaque jour (jamais 14:00 comme le disait
# l'ancienne version). On liste donc le répertoire HTTP et on prend TOUS les
# tarballs de la fenêtre visée. Idempotent : parse_dila_bulk.py fait
# INSERT OR IGNORE/REPLACE → ré-ingérer une décision déjà présente = no-op.
#
# ⚠️ POURQUOI UNE FENÊTRE, ET PAS SEULEMENT LA VEILLE (29 août 2026)
# L'ancienne version ne demandait QUE les tarballs de J-1. Toute journée
# ratée — DILA indisponible, réseau coupé, parse en échec, machine éteinte —
# était perdue DÉFINITIVEMENT : rien ne revenait jamais la chercher, et
# aucune alerte ne le signalait. C'est le même défaut que celui corrigé en
# août 2026 sur judilibre_sync.py, resté ici parce qu'on n'avait corrigé
# qu'un tuyau sur deux.
# Désormais : on regarde les WINDOW_DAYS derniers jours et on applique tout
# ce qui n'est pas déjà au registre. Un tarball n'entre au registre QUE si
# son parse a réussi — un échec est donc automatiquement retenté la nuit
# suivante, jusqu'à ce qu'il passe ou sorte de la fenêtre.
set -e
LOG=/var/log/justicelibre/dila_update.log
WORK=/opt/justicelibre/dila_bulk
mkdir -p "$WORK" /var/log/justicelibre

# ⚠️ VERROU. Ce script ET dila_catchup.sh téléchargent dans le MÊME fichier
# temporaire ($WORK/Freemium_<fond>.tar.gz), parce que parse_dila_bulk.py
# attend ce nom fixe. Deux exécutions simultanées se marcheraient dessus :
# l'une parserait le tarball de l'autre, avec ingestion silencieusement
# fausse à la clé. Un rattrapage long qui déborde sur 4 h du matin suffit à
# déclencher le cas. On sérialise donc les ingestions.
exec 9>"$WORK/.ingest.lock"
if ! flock -n 9; then
  echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] une autre ingestion DILA est en cours — on passe notre tour (les tarballs non traités seront repris demain, ils ne sont pas au registre)" >> "$LOG"
  exit 0
fi

# Fonds à mettre à jour : TOUS les bulks DILA que ce serveur héberge.
# NB: judiciaire.db (côté PROD) a son propre cron via Judilibre PISTE, il
# ne dépend pas de ces bulks pour rester frais.
FUNDS=(legi jorf jade kali cnil cass capp constit inca)

# Largeur de la fenêtre de rattrapage, en jours. 10 couvre un week-end
# prolongé + quelques jours d'indisponibilité sans jamais rien perdre.
WINDOW_DAYS="${DILA_WINDOW_DAYS:-10}"

echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] DILA daily update — fenêtre ${WINDOW_DAYS}j" >> "$LOG"

for fund in "${FUNDS[@]}"; do
  FUND_UP="${fund^^}"
  LEDGER="$WORK/.applied_${fund}"
  touch "$LEDGER"

  # Listing HTTP une seule fois par fond.
  LISTING=$(curl -sS --max-time 120 "https://echanges.dila.gouv.fr/OPENDATA/${FUND_UP}/" || true)
  if [ -z "$LISTING" ]; then
    echo "[$(date -u '+%H:%M:%S')] $fund: listing DILA injoignable, fond ignoré ce soir" >> "$LOG"
    continue
  fi

  # Tarballs de la fenêtre [J-WINDOW_DAYS ; J-1], toutes heures confondues.
  CANDIDATS=""
  for d in $(seq 1 "$WINDOW_DAYS"); do
    JOUR=$(date -u -d "$d days ago" +%Y%m%d)
    CANDIDATS="$CANDIDATS $(echo "$LISTING" \
      | grep -oE "${FUND_UP}_${JOUR}-[0-9]+\.tar\.gz" | sort -u)"
  done
  CANDIDATS=$(echo "$CANDIDATS" | tr ' ' '\n' | grep -v '^$' | sort -u || true)

  # Premier passage (registre vide) : on considère l'historique comme déjà
  # ingéré et on ne traite que la veille. Évite de rejouer toute la fenêtre
  # la première nuit ; la protection joue à plein dès le lendemain.
  if [ ! -s "$LEDGER" ]; then
    HIER=$(date -u -d "yesterday" +%Y%m%d)
    echo "$CANDIDATS" | grep -v "_${HIER}-" >> "$LEDGER" || true
    echo "[$(date -u '+%H:%M:%S')] $fund: registre initialisé (historique considéré ingéré)" >> "$LOG"
  fi

  # Ne garder que ce qui n'a jamais été appliqué avec succès.
  A_FAIRE=$(comm -23 <(echo "$CANDIDATS") <(sort -u "$LEDGER") || true)
  N=$(echo "$A_FAIRE" | grep -c . || true)
  if [ "$N" -eq 0 ]; then
    echo "[$(date -u '+%H:%M:%S')] $fund: à jour" >> "$LOG"
    continue
  fi
  echo "[$(date -u '+%H:%M:%S')] $fund: $N tarball(s) manquant(s) à appliquer" >> "$LOG"

  for tb in $A_FAIRE; do
    url="https://echanges.dila.gouv.fr/OPENDATA/${FUND_UP}/${tb}"
    out="$WORK/Freemium_${fund}.tar.gz"
    echo "[$(date -u '+%H:%M:%S')] $fund: fetch $tb" >> "$LOG"
    if ! curl -sf --max-time 600 "$url" -o "$out"; then
      # PAS d'entrée au registre → retenté demain.
      echo "[$(date -u '+%H:%M:%S')] $fund: download FAILED (sera retenté)" >> "$LOG"
      continue
    fi
    size=$(stat -c%s "$out")
    if [ "$size" -lt 200 ]; then
      # Tarball vide côté DILA : rien à ingérer, on le marque fait pour ne
      # pas le retélécharger chaque nuit.
      echo "[$(date -u '+%H:%M:%S')] $fund: empty (${size}b), skip" >> "$LOG"
      echo "$tb" >> "$LEDGER"
      rm -f "$out"
      continue
    fi
    cd /opt/justicelibre
    if timeout 900 python3 -u parse_dila_bulk.py "$fund" >> "$LOG" 2>&1; then
      echo "[$(date -u '+%H:%M:%S')] $fund: parse OK ($(du -h $out | cut -f1))" >> "$LOG"
      echo "$tb" >> "$LEDGER"          # succès : ne sera plus rejoué
    else
      # PAS d'entrée au registre → retenté demain, et les nuits suivantes.
      echo "[$(date -u '+%H:%M:%S')] $fund: parse FAILED (sera retenté)" >> "$LOG"
    fi
    rm -f "$out"
  done

  # Le registre ne sert que sur la fenêtre : on le borne pour qu'il ne
  # grossisse pas indéfiniment (2 ans de noms de tarballs suffisent).
  tail -n 800 "$LEDGER" > "$LEDGER.tmp" && mv "$LEDGER.tmp" "$LEDGER"
done

echo "[$(date -u '+%H:%M:%S')] daily update done" >> "$LOG"
