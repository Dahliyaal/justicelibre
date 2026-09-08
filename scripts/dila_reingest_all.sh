#!/bin/bash
# Ré-ingestion COMPLÈTE des fonds DILA avec le parseur réparé (8 sept. 2026).
#
# Pourquoi : cinq pannes de parseur (KALI vide, jointure LEGI morte, JORF sans
# corps, jurisprudence sans enrichissement sur les deltas, CNIL) et des dizaines
# de champs jetés. Le code est réparé (commit 98b86c5) ; les données, elles,
# ne se réparent que par une ré-ingestion : le GLOBAL du 13/07/2025, PUIS tous
# les deltas quotidiens dans l'ordre chronologique (sinon les textes reviennent
# à leur état de juillet 2025). LEGI est le seul fonds dont la clé
# (legiarti, date_debut) rend l'ordre indifférent.
#
# Garde-fous : verrou partagé avec le cron de 4 h ; sauvegarde AVANT (script
# séparé, à lancer d'abord) ; migration = ADD COLUMN seulement ; arrêt propre
# sous 8 Go libres ; chaque tarball est loggé ; les deltas sont effacés après
# parse, les globals conservés dans dila_bulk/ ; reprenable (registre
# .reingest_done_<fond>).
#
#   systemd-run --unit=jl-reingest-dila /bin/bash /opt/justicelibre/scripts/dila_reingest_all.sh
#   tail -f /var/log/justicelibre/reingest.log
set -u
cd /opt/justicelibre
WORK=/opt/justicelibre/dila_bulk
LOG=/var/log/justicelibre/reingest.log
DELTAS=$WORK/deltas
MIN_FREE_GO=8
mkdir -p "$DELTAS" /var/log/justicelibre
exec 9>"$WORK/.ingest.lock"
flock 9
log() { echo "[$(date -u '+%F %T')] $*" >> "$LOG"; }
libre_go() { df --output=avail -BG / | tail -1 | tr -dc '0-9'; }
guard() { if [ "$(libre_go)" -lt "$MIN_FREE_GO" ]; then log "⛔ disque < ${MIN_FREE_GO} Go libres — arrêt propre"; exit 3; fi; }

log "===== RÉ-INGESTION DILA — début ; disque libre $(libre_go) Go"
# 1) migration de schéma (ADD COLUMN seulement, idempotent)
python3 scripts/migrate_schema_dila.py --db-dir dila --apply >> "$LOG" 2>&1 || { log "⛔ migration en échec"; exit 4; }

compte() {  # compte <fond> <table> <col1,col2,...>
  local db="dila/$1.db" t="$2" cols="$3" sql="SELECT COUNT(*)"
  for c in ${cols//,/ }; do sql="$sql, SUM($c IS NOT NULL AND $c<>'')"; done
  log "  $1/$t lignes,${cols} = $(sqlite3 "$db" "$sql FROM $t" 2>&1)"
}
COLS_constit="ecli,nature_qualifiee,url_cc";  T_constit=constit_decisions
COLS_cnil="date,nature_delib";                T_cnil=cnil_deliberations
COLS_kali="idcc,titre,date_debut";             T_kali=kali_textes
COLS_capp="siege_appel,abstrats,liens_textes"; T_capp=capp_decisions
COLS_cass="avocat_general,form_dec_att,abstrats"; T_cass=cass_decisions
COLS_inca="publi_bull,form_dec_att";           T_inca=inca_decisions
COLS_jade="abstrats,type_rec,liens_textes";    T_jade=jade_decisions
COLS_legi="legitext,hierarchie,liens";         T_legi=legi_articles
COLS_jorf="texte,id_eli,liens";                T_jorf=jorf_textes

reingest() {  # reingest <fond>
  local f="$1" U="${1^^}" done_reg="$WORK/.reingest_done_$1"
  touch "$done_reg"
  local tvar="T_$f" cvar="COLS_$f"
  log "----- $f : AVANT"; compte "$f" "${!tvar}" "${!cvar}"
  local listing; listing=$(curl -sS --max-time 120 "https://echanges.dila.gouv.fr/OPENDATA/$U/") || { log "  listing DILA injoignable, $f sauté"; return 1; }
  local global; global=$(echo "$listing" | grep -oE "Freemium_${f}_global_[0-9]{8}-[0-9]+\.tar\.gz" | sort -u | tail -1)
  local gdate; gdate=$(echo "$global" | grep -oE "[0-9]{8}" | head -1)
  # global
  if ! grep -qx "$global" "$done_reg"; then
    guard
    if [ ! -s "$WORK/$global" ]; then
      log "  téléchargement $global"
      curl -sf --max-time 3600 "https://echanges.dila.gouv.fr/OPENDATA/$U/$global" -o "$WORK/$global.part" && mv "$WORK/$global.part" "$WORK/$global" || { log "  ⛔ téléchargement global échoué"; return 1; }
    fi
    log "  parse GLOBAL $global"
    if python3 -u parse_dila_bulk.py "$f" --tarball "$WORK/$global" >> "$LOG" 2>&1; then echo "$global" >> "$done_reg"; else log "  ⛔ parse global échoué, $f interrompu"; return 1; fi
  else log "  global déjà fait"; fi
  # deltas chronologiques depuis la date du global
  local tbs; tbs=$(echo "$listing" | grep -oE "${U}_[0-9]{8}-[0-9]+\.tar\.gz" | sort -u | awk -v since="$gdate" -F_ '{split($2,a,"-"); if (a[1] >= since) print}')
  local n; n=$(echo "$tbs" | grep -c . || true); local i=0 ko=0
  log "  $n deltas à rejouer"
  for tb in $tbs; do
    i=$((i+1))
    grep -qx "$tb" "$done_reg" && continue
    guard
    if ! curl -sf --max-time 600 "https://echanges.dila.gouv.fr/OPENDATA/$U/$tb" -o "$DELTAS/$tb"; then log "  [$i/$n] $tb : téléchargement échoué"; ko=$((ko+1)); continue; fi
    if [ "$(stat -c%s "$DELTAS/$tb")" -lt 200 ]; then echo "$tb" >> "$done_reg"; rm -f "$DELTAS/$tb"; continue; fi
    if python3 -u parse_dila_bulk.py "$f" --tarball "$DELTAS/$tb" >> "$LOG" 2>&1; then echo "$tb" >> "$done_reg"; echo "$tb" >> "$WORK/.applied_$f"; else log "  [$i/$n] $tb : parse ÉCHOUÉ"; ko=$((ko+1)); fi
    rm -f "$DELTAS/$tb"
    [ $((i % 50)) -eq 0 ] && log "  [$i/$n] deltas… disque $(libre_go) Go"
  done
  sqlite3 "dila/$f.db" "PRAGMA wal_checkpoint(TRUNCATE)" >/dev/null 2>&1
  log "----- $f : APRÈS ($ko échec(s) sur $n deltas)"; compte "$f" "${!tvar}" "${!cvar}"
}

for f in constit cnil kali capp cass inca jade legi jorf; do
  reingest "$f" || log "⚠️ $f incomplet — voir ci-dessus"
done
log "===== RÉ-INGESTION DILA — fin ; disque libre $(libre_go) Go"
