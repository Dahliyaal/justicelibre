#!/bin/bash
# Purge RGPD mensuelle des signalements utilisateur (> 12 mois).
# Promis dans /confidentialite.html ("Conservation : 12 mois maximum.
# Purge automatique mensuelle au-delà.") — ce script tient la promesse.
#
# Install :
#   chmod +x /opt/justicelibre/scripts/purge_feedback.sh
#   crontab -e :
#     0 3 1 * * /opt/justicelibre/scripts/purge_feedback.sh
set -e
F=/var/log/justicelibre/feedback.jsonl
[ -f "$F" ] || exit 0
python3 - <<'EOF'
import json, time, os
F = "/var/log/justicelibre/feedback.jsonl"
cutoff = time.time() - 365 * 86400
kept, dropped = [], 0
with open(F, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            if json.loads(line).get("ts", 0) >= cutoff:
                kept.append(line)
            else:
                dropped += 1
        except json.JSONDecodeError:
            dropped += 1
tmp = F + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    f.write("\n".join(kept) + ("\n" if kept else ""))
os.replace(tmp, F)
print(f"purge_feedback: {dropped} entrée(s) purgée(s), {len(kept)} conservée(s)")
EOF
