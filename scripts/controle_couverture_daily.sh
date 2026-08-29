#!/bin/bash
# Contrôle de couverture quotidien : demande à chaque source combien elle a,
# compare à ce qu'on a, et crie en cas d'écart.
#
# Pourquoi (30 août 2026) : un trou de données ne produit AUCUN symptôme.
# Le 29 août 2026, 248 250 décisions judiciaires manquaient sur les huit
# premiers mois de l'année sans que rien ne l'indique — pages correctes,
# filtres fonctionnels, compteurs justes. Quatre mois d'audits de code
# n'avaient rien vu, parce que le code était correct. Seule une référence
# EXTÉRIEURE peut détecter ça.
#
# Install :
#   chmod +x /opt/justicelibre/scripts/controle_couverture_daily.sh
#   crontab -e :
#     0 6 * * * /bin/bash /opt/justicelibre/scripts/controle_couverture_daily.sh
# (6h00 UTC : après la synchro judilibre de 4h30 et les scrapers de 5h, pour
#  contrôler l'état APRÈS le travail de la nuit.)
#
# ⚠️ Appelé via `/bin/bash script.sh`, jamais par le bit d'exécution : un
# déploiement qui ne préserve pas les permissions a déjà tué trois pipelines
# en silence (constaté le 29 août 2026).

set -a; source /opt/justicelibre/.env; set +a

LOG=/var/log/justicelibre/couverture.log
ALERTES=/var/log/justicelibre/couverture_alertes.txt
mkdir -p /var/log/justicelibre
cd /opt/justicelibre

{
  echo "════════════════════════════════════════════════════════"
  echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] contrôle de couverture"
} >> "$LOG"

SORTIE=$(timeout 900 python3 -u scripts/controle_couverture.py --mois 2 --annees 2 2>&1)
CODE=$?

echo "$SORTIE" >> "$LOG"

# Le fichier d'alertes ne contient QUE l'état courant : s'il est vide, tout
# va bien. Il est réécrit à chaque passage, jamais accumulé — une alerte
# résolue doit disparaître, sinon on s'habitue à la voir et on ne la lit plus.
if [ "$CODE" -eq 1 ]; then
  {
    echo "Dernier contrôle : $(date -u '+%Y-%m-%d %H:%M:%S') UTC"
    echo
    echo "$SORTIE" | sed -n '/ALERTE/,$p'
  } > "$ALERTES"
  echo "[$(date -u '+%H:%M:%S')] ⚠️  alertes écrites dans $ALERTES" >> "$LOG"
else
  : > "$ALERTES"
  echo "[$(date -u '+%H:%M:%S')] ✓ aucune alerte" >> "$LOG"
fi
