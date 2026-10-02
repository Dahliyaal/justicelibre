# Maintenance nocturne de la prod (unattended-upgrades) — proposition, NON appliquée

Audit du 2 oct. 2026, défaut P3 : 274 `POST /mcp 502` le 02/10 entre 06:49 et 06:50.

## Ce qui s'est passé (journaux de la prod, lus le 2/10)

1. `apt-daily-upgrade.timer` : `OnCalendar=*-*-* 6:00`, `RandomizedDelaySec=60m` → lancé à 06:48:51.
2. unattended-upgrades installe `openssl`, `libssl3t64`, `libssl-dev`, `libheif*`, `libauthen-sasl-perl` (06:49:00 → 06:50:47).
3. needrestart (3.6-7ubuntu4.5, `$nrconf{restart}` non défini, donc automatique en mode non interactif) relance tout ce qui charge libssl : à 06:49:14 systemd arrête fail2ban, nginx, ssh, journald, justicelibre-token et justicelibre.
4. nginx et le token sont revenus en 1 s (06:49:15). **Le MCP non** : uvicorn attend la fermeture des flux SSE (« Waiting for connections to close »), ne sort pas, et systemd le tue au bout du `TimeoutStopSec` par défaut, 90 s (« State 'stop-sigterm' timed out. Killing. », 06:50:44). Le nouveau processus démarre en 2 s.

Donc la coupure de 90 s vient surtout du délai d'arrêt du MCP. Elle touche aussi chaque déploiement et chaque `systemctl restart justicelibre`.

## Les trois fichiers

| fichier du dépôt | à copier vers | effet |
|---|---|---|
| `justicelibre.service.d/arret-rapide.conf` | `/etc/systemd/system/justicelibre.service.d/arret-rapide.conf` | `TimeoutStopSec=8s` : un redémarrage coupe ~10 s au lieu de 90 s. **Le correctif principal.** |
| `apt-daily-upgrade.timer.d/override.conf` | `/etc/systemd/system/apt-daily-upgrade.timer.d/override.conf` | mises à jour à 02:30 UTC (+0 à 20 min) au lieu de 06:00-07:00, dans le creux du trafic. |
| `needrestart-conf.d/90-justicelibre.conf` | `/etc/needrestart/conf.d/90-justicelibre.conf` | **OPTIONNEL.** needrestart ne relance plus nginx ni justicelibre*. Plus de coupure, mais un correctif de libssl n'est pris par nginx et le MCP qu'au prochain redémarrage manuel. |

Recommandation : appliquer les deux premiers. Le troisième seulement si une coupure de ~10 s à 02:30 UTC est encore de trop ; dans ce cas, redémarrer à la main après chaque mise à jour de sécurité (`needrestart -b` liste les services en attente).

## Application (par l'opératrice, sur 46.225.190.237)

```bash
install -d /etc/systemd/system/justicelibre.service.d /etc/systemd/system/apt-daily-upgrade.timer.d
install -m 644 arret-rapide.conf /etc/systemd/system/justicelibre.service.d/
install -m 644 override.conf     /etc/systemd/system/apt-daily-upgrade.timer.d/
systemctl daemon-reload
systemctl restart apt-daily-upgrade.timer
# Vérifications (aucun redémarrage du MCP nécessaire, la valeur est lue à l'arrêt) :
systemctl show justicelibre -p TimeoutStopUSec        # attendu : TimeoutStopUSec=8s
systemctl list-timers apt-daily-upgrade.timer          # NEXT vers 02:30-02:50 UTC
# Optionnel :
install -m 644 90-justicelibre.conf /etc/needrestart/conf.d/
needrestart -b                                         # doit tourner sans erreur Perl
```

Contrôle le lendemain : `grep ' 502 ' /var/log/nginx/access.log | grep 'POST /mcp' | cut -c1-40 | sort | uniq -c` et `journalctl -u justicelibre --since today | grep -i 'timed out'` (doit être vide).

## Retour arrière

```bash
rm /etc/systemd/system/justicelibre.service.d/arret-rapide.conf
rm /etc/systemd/system/apt-daily-upgrade.timer.d/override.conf
rm -f /etc/needrestart/conf.d/90-justicelibre.conf
systemctl daemon-reload
systemctl restart apt-daily-upgrade.timer
systemctl show justicelibre -p TimeoutStopUSec        # revient à 1min 30s
systemctl list-timers apt-daily-upgrade.timer          # revient vers 06:00-07:00
```

Rien d'autre n'est modifié : `50unattended-upgrades`, `20auto-upgrades` et `needrestart.conf` restent ceux du paquet.

## Risque à connaître

Avec `TimeoutStopSec=8s`, une requête MCP longue en cours (ex. `search_cc` lent) est coupée net au redémarrage au lieu d'avoir 90 s pour finir. Le client reçoit une erreur de connexion et peut réessayer ; c'était déjà le cas des flux SSE, tués au bout de 90 s.
