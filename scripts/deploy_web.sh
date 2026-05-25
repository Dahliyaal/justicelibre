#!/usr/bin/env bash
# Déploie les pages statiques vers PROD (/var/www/justicelibre) en stampant
# automatiquement la date de "MàJ" = date du dernier commit git, dans
# version.json. Le badge sur la landing la lit en JS → plus jamais de date en
# dur à bumper à la main.
set -euo pipefail
cd "$(dirname "$0")/.."
D=$(git log -1 --format=%cd --date=format:%Y-%m-%d)
printf '{"updated":"%s"}\n' "$D" > web/version.json
rsync -az web/index.html web/ressources.html web/version.json \
  root@46.225.190.237:/var/www/justicelibre/
echo "Web déployé. MàJ = $D"
