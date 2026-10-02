#!/usr/bin/env python3 -u
"""Scrape ArianeWeb (Conseil d'État) en aspirant les ~270k décisions
via le plugin Sinequa downloadFilePagePlugin.

Strategy : énumérer les IDs internes ArianeWeb /Ariane_Web/AW_DCE/|N
de 1 à START_MAX, fetch le texte pour chaque, skip ceux déjà en DB.

Circuit breaker : si N erreurs consécutives, on stoppe le script.
"""
import html as _html
import itertools
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import httpx

sys.stdout.reconfigure(line_buffering=True)

DB_PATH = "/opt/justicelibre/dila/judiciaire.db"
DOWNLOAD_URL = "https://www.conseil-etat.fr/plugin"
USER_AGENT = "justicelibre.org/1.0 (open data, contact: dahliyaal@justicelibre.org)"
SLEEP_BETWEEN_REQUESTS = 0.30  # 3 req/s, polite
MAX_CONSECUTIVE_ERRORS = 30    # circuit breaker (erreurs réseau/500)
# Plage d'IDs actifs ArianeWeb observée par probing :
#   id=50000    → 404
#   id=100000   → 200
#   id=219809   → 200
#   id=239895   → 200  (CE 19/05/2022 n°461534 — au-dessus de l'ancien plafond 235k)
# PAS DE PLAFOND HAUT : tout END_ID fixe finit par devenir trop bas (le CE
# produit des décisions en continu, les IDs internes montent indéfiniment).
# La boucle balaie depuis START_ID sans borne ; le SEUL juge de la fin est le
# circuit breaker 404 (MAX_CONSECUTIVE_404 vides consécutifs = vrai plafond du
# jour). Chaque run re-détecte donc automatiquement le sommet courant.
# Reprise via checkpoint.
START_ID = 95_000
MAX_CONSECUTIVE_404 = 5_000    # tolère les trous; déclenche une reconnaissance
# Les identifiants ArianeWeb ne sont pas contigus : le corpus comporte des trous
# de PLUS de 5 000 identifiants. Constaté le 9 septembre 2026 : la moisson s'est
# arrêtée à l'id 222319 en concluant « fin du corpus », alors que 223000, 230000,
# 233000, 239895 et 245000 répondent tous 200. Le checkpoint était réécrit à
# 222319 à chaque passage, donc le cron quotidien retombait dans le même trou :
# aucune décision du Conseil d'État n'est entrée depuis le 12 décembre 2025.
# Avant de conclure à la fin, on sonde loin devant ; on ne s'arrête que si TOUTES
# les sondes sont vides. La sonde décide SEULEMENT s'il faut continuer : on ne
# saute jamais par-dessus le trou. Les identifiants sont trop dispersés pour ça
# (242000 est vide, 245000 vivant, 250000 vide, 251000 vivant) : sauter perdrait
# des décisions en silence, ce qui est exactement le défaut qu'on répare.
# Balayer un trou coûte 404 x 0,3 s, on peut se le permettre.
SONDES = (2_000, 5_000, 10_000, 20_000, 40_000, 80_000)

# ⛔ PAS dans /tmp. La prod tourne avec `fs.protected_regular = 2` : le noyau
# refuse à TOUT LE MONDE, root compris, d'ouvrir en écriture un fichier situé
# dans un répertoire collant et ouvert à tous (/tmp, 1777, à root) dès lors que
# le fichier appartient à quelqu'un d'autre — ici justicelibre. Le checkpoint
# était donc condamné à rester figé, en silence (constaté le 10/09/2026 : resté
# à 243481 alors que la moisson était montée à 330749). /tmp est en outre vidé
# au redémarrage. Le répertoire applicatif appartient à justicelibre, qui fait
# tourner la tâche quotidienne.
CHECKPOINT_FILE = "/opt/justicelibre/scrape_ariane.checkpoint"


def ensure_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS ariane_decisions (
        ariane_id TEXT PRIMARY KEY,        -- /Ariane_Web/AW_DCE/|NNNNNN
        ariane_num INTEGER,                -- juste le NNNNNN
        text TEXT,
        fetched_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_ariane_num ON ariane_decisions(ariane_num);
    CREATE VIRTUAL TABLE IF NOT EXISTS ariane_fts USING fts5(
        ariane_id UNINDEXED, text,
        content='ariane_decisions', content_rowid='rowid'
    );
    CREATE TRIGGER IF NOT EXISTS ariane_ai AFTER INSERT ON ariane_decisions BEGIN
        INSERT INTO ariane_fts(rowid, ariane_id, text)
        VALUES (new.rowid, new.ariane_id, new.text);
    END;
    CREATE TRIGGER IF NOT EXISTS ariane_ad AFTER DELETE ON ariane_decisions BEGIN
        INSERT INTO ariane_fts(ariane_fts, rowid, ariane_id, text)
        VALUES ('delete', old.rowid, old.ariane_id, old.text);
    END;
    CREATE TRIGGER IF NOT EXISTS ariane_au AFTER UPDATE ON ariane_decisions BEGIN
        INSERT INTO ariane_fts(ariane_fts, rowid, ariane_id, text)
        VALUES ('delete', old.rowid, old.ariane_id, old.text);
        INSERT INTO ariane_fts(rowid, ariane_id, text)
        VALUES (new.rowid, new.ariane_id, new.text);
    END;
    """)
    conn.commit()


def clean_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_one(client, num: int) -> str | None:
    """Retourne texte si succès, None si 404, lève si erreur réseau."""
    aid = f"/Ariane_Web/AW_DCE/|{num}"
    r = client.get(DOWNLOAD_URL, params={
        "plugin": "Service.downloadFilePagePlugin",
        "Index": "Ariane_Web",
        "Id": aid,
    }, timeout=30)
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    # /plugin déclare iso-8859-1 mais envoie parfois de l'UTF-8 valide
    # (constaté le 7 août 2026) : UTF-8 strict d'abord (auto-validant),
    # repli sur l'iso-8859-1 annoncé. Cf. sources/ariane.py.
    try:
        raw = r.content.decode("utf-8")
    except UnicodeDecodeError:
        raw = r.content.decode("iso-8859-1")
    text = clean_html(raw)
    if len(text) < 200:
        return None
    return text


def load_checkpoint(conn=None) -> int:
    """Point de reprise : le PLUS GRAND du fichier et du sommet réel en base.

    La base fait autorité, le fichier n'est qu'un raccourci. Le 9 septembre 2026
    la moisson a tourné en root alors que le fichier appartient à l'utilisateur
    justicelibre : l'écriture a échoué, l'échec était avalé (`except: pass`), et
    le fichier est resté à 243481 alors que le balayage était monté à 330749.
    La tâche quotidienne serait repartie 87 000 identifiants en arrière, soit
    environ 7 h de balayage pour n'ajouter rien du tout.
    """
    depuis_fichier = START_ID
    try:
        depuis_fichier = int(Path(CHECKPOINT_FILE).read_text().strip())
    except Exception as e:
        print(f"[ariane] pas de checkpoint lisible ({e}) — on se fie à la base")
    depuis_base = 0
    if conn is not None:
        try:
            depuis_base = conn.execute(
                "SELECT COALESCE(MAX(ariane_num), 0) FROM ariane_decisions").fetchone()[0]
        except Exception as e:
            print(f"[ariane] sommet en base illisible ({e})")
    if depuis_base > depuis_fichier:
        print(f"[ariane] checkpoint {depuis_fichier} en retard sur la base "
              f"({depuis_base}) — on repart du sommet réel")
        return depuis_base
    # Un checkpoint AU-DELÀ du sommet en base est un point de reprise
    # mensonger : le checkpoint n'enregistre plus que des identifiants vivants
    # (donc en base). Du 11/09 au 2/10/2026 il valait « dernier vivant + 5 000 »
    # et avançait de 5 000 par jour (325793 → 430775) pendant que toutes les
    # décisions publiées depuis le 9/09 (ids 325794+) étaient sautées (audit du
    # 2 oct. 2026, F2). La base fait autorité.
    if depuis_base and depuis_fichier > depuis_base:
        print(f"[ariane] checkpoint {depuis_fichier} AU-DELÀ du sommet en base "
              f"({depuis_base}) — ignoré, on repart du sommet réel")
        return depuis_base
    return depuis_fichier


def save_checkpoint(n: int):
    # ⛔ ne JAMAIS taire l'échec : c'est lui qui a fait repartir la moisson
    # 87 000 identifiants en arrière le 9 septembre 2026, sans un mot.
    try:
        Path(CHECKPOINT_FILE).write_text(str(n))
    except Exception as e:
        print(f"  [checkpoint NON ENREGISTRÉ id={n}] {e} — "
              f"la reprise se fera sur le sommet en base")


# Alerte : 0 décision nouvelle au sommet depuis plus de N jours = moisson morte.
ALERTE_JOURS = int(os.environ.get("ARIANE_ALERTE_JOURS", "3") or 3)
EXIT_MOISSON_MORTE = 3


def jours_depuis_sommet(conn) -> float | None:
    """Âge (jours) de la décision au plus grand ariane_num (index idx_ariane_num).

    ⛔ Pas de MAX(fetched_at) : colonne sans index, ~8 min de lecture sur la
    prod (audit du 2 oct. 2026).
    """
    try:
        row = conn.execute(
            "SELECT julianday('now') - julianday(fetched_at) FROM ariane_decisions "
            "ORDER BY ariane_num DESC LIMIT 1").fetchone()
        return float(row[0]) if row and row[0] is not None else None
    except Exception as e:
        print(f"[ariane] âge du sommet illisible ({e})")
        return None


def bilan(conn, added_session: int, borne: bool) -> int:
    """Dit franchement ce que la session a rapporté ; code de sortie."""
    if added_session > 0:
        return 0
    age = jours_depuis_sommet(conn)
    age_txt = f"{age:.1f} j" if age is not None else "inconnu"
    print(f"[ariane] 0 nouvelle décision cette session (dernière décision du sommet "
          f"moissonnée il y a {age_txt})")
    if not borne and age is not None and age > ALERTE_JOURS:
        print(f"[ariane] ERREUR : aucune décision nouvelle depuis plus de {ALERTE_JOURS} j "
              f"— moisson probablement morte (code {EXIT_MOISSON_MORTE})")
        return EXIT_MOISSON_MORTE
    return 0


def reconnaitre(client, depuis: int) -> int | None:
    """Cherche un identifiant vivant au-delà d'un trou. Renvoie None si le corpus est fini.

    Six sondes espacées (2 k à 80 k) suffisent : le plus grand trou observé fait
    moins de 20 000 identifiants, et le sommet du corpus est autour de 250 000.
    Sert uniquement à répondre « le corpus continue-t-il ? ». L'appelant ne saute
    pas jusqu'à la sonde : il reprend son balayage là où il était.
    """
    for pas in SONDES:
        cible = depuis + pas
        try:
            if fetch_one(client, cible) is not None:
                return cible
        except Exception as e:
            print(f"  [sonde id={cible}] {e}")
        time.sleep(SLEEP_BETWEEN_REQUESTS)
    return None


def main():
    print(f"[ariane] start ; UA = {USER_AGENT}")
    conn = sqlite3.connect(DB_PATH, timeout=120.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA recursive_triggers=ON")  # INSERT OR REPLACE doit déclencher le trigger _ad du FTS5
    conn.execute("PRAGMA busy_timeout=120000")
    conn.execute("PRAGMA cache_size=-32000")
    ensure_schema(conn)

    existing = conn.execute("SELECT COUNT(*) FROM ariane_decisions").fetchone()[0]
    print(f"[ariane] DB existing : {existing}")

    start_at = load_checkpoint(conn)
    # Balayage BORNÉ, pour rattraper une zone précise sans toucher au checkpoint
    # de la tâche quotidienne (qui, lui, reprend au sommet de la base). Motif :
    # l'audit du 10/09/2026 a trouvé ~40 000 identifiants vivants SOUS
    # START_ID = 95 000 (l'id 70 000 est un arrêt de Section de 1983) — le
    # plancher n'avait jamais été exploré, seul le plafond l'était.
    #   ARIANE_DEPUIS=55000 ARIANE_JUSQUA=95000 python3 -u scrape_ariane.py
    depuis = int(os.environ.get("ARIANE_DEPUIS", "0") or 0)
    jusqua = int(os.environ.get("ARIANE_JUSQUA", "0") or 0)
    if depuis:
        start_at = depuis
        print(f"[ariane] balayage borné demandé : {depuis} → {jusqua or '∞'}")
    print(f"[ariane] resume from id={start_at}")
    borne = bool(depuis)
    # Le checkpoint n'enregistre JAMAIS que le dernier identifiant vivant
    # (récupéré ou déjà en base), jamais l'identifiant atteint par le balayage
    # (audit du 2 oct. 2026, F2). Un balayage borné ne le touche pas.
    dernier_vivant = start_at

    def ckpt():
        if not borne:
            save_checkpoint(dernier_vivant)

    client = httpx.Client(headers={"User-Agent": USER_AGENT})
    consecutive_errors = 0
    consecutive_404 = 0
    consecutive_skipped = 0
    added_session = 0
    start_t = time.time()

    trous_franchis = 0
    for num in itertools.count(start_at):
        if jusqua and num > jusqua:
            print(f"[ariane] borne {jusqua} atteinte : fin du balayage borné")
            break
        # Skip si déjà en DB
        existing_row = conn.execute(
            "SELECT length(text) FROM ariane_decisions WHERE ariane_num=?", (num,)
        ).fetchone()
        if existing_row and existing_row[0] and existing_row[0] > 200:
            # Une décision déjà en base PROUVE que cet identifiant est vivant :
            # elle doit donc casser la série de 404, exactement comme un fetch
            # réussi. Sans cette remise à zéro, une zone déjà moissonnée (donc
            # saine) accumulait ses seuls trous et atteignait les 5 000 « 404
            # consécutifs » — d'où un faux « fin du corpus ». Mesuré le
            # 9/09/2026 : le balayage a déclaré morte la plage 238482-243481,
            # alors que 238500, 239895, 241000, 243005 et 243400 répondent tous
            # 200 — ils étaient simplement déjà en base.
            consecutive_404 = 0
            consecutive_skipped += 1
            dernier_vivant = max(dernier_vivant, num)
            if consecutive_skipped % 1000 == 0:
                print(f"  [skip x{consecutive_skipped}] at id={num}")
                ckpt()
            continue
        consecutive_skipped = 0

        try:
            text = fetch_one(client, num)
        except Exception as e:
            consecutive_errors += 1
            print(f"  [err {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}] id={num}: {e}")
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print(f"\n*** CIRCUIT BREAKER ***")
                print(f"  {MAX_CONSECUTIVE_ERRORS} erreurs consécutives, arrêt.")
                print(f"  Dernier id tenté : {num} ; dernier vivant : {dernier_vivant}")
                ckpt()
                sys.exit(2)
            time.sleep(min(60, 5 * consecutive_errors))  # backoff
            continue
        consecutive_errors = 0

        if text is None:
            consecutive_404 += 1
            if consecutive_404 >= MAX_CONSECUTIVE_404:
                vivant = reconnaitre(client, num)
                if vivant is None:
                    print(f"\n*** {MAX_CONSECUTIVE_404} x 404 puis {len(SONDES)} sondes vides jusqu'à "
                          f"id={num + SONDES[-1]} : fin du corpus "
                          f"(dernier vivant : {dernier_vivant}).")
                    ckpt()
                    break
                print(f"  [trou] {consecutive_404} x 404 depuis id={num - consecutive_404 + 1} ; "
                      f"le corpus continue (id={vivant} répond) — on poursuit sans sauter")
                consecutive_404 = 0
                trous_franchis += 1
            # Un 404 est une requête comme une autre : on tient la cadence
            # annoncée. Sans cette pause, le balayage d'un trou partait à
            # ~20 req/s, très au-delà des 3 req/s que l'en-tête promet.
            time.sleep(SLEEP_BETWEEN_REQUESTS)
            continue
        consecutive_404 = 0

        # Insert
        try:
            conn.execute(
                "INSERT OR REPLACE INTO ariane_decisions (ariane_id, ariane_num, text, fetched_at) VALUES (?,?,?,datetime('now'))",
                (f"/Ariane_Web/AW_DCE/|{num}", num, text),
            )
            conn.commit()
            added_session += 1
            dernier_vivant = max(dernier_vivant, num)
        except Exception as e:
            print(f"  [DB err id={num}] {e}")

        if added_session % 50 == 0:
            elapsed = time.time() - start_t
            rate = added_session / elapsed if elapsed > 0 else 0
            print(f"  +{added_session} added (id={num}, {rate:.1f}/s)")
            ckpt()

        time.sleep(SLEEP_BETWEEN_REQUESTS)

    ckpt()
    final = conn.execute("SELECT COUNT(*) FROM ariane_decisions").fetchone()[0]
    print(f"\nDONE. Total ariane : {final} (+{added_session} cette session, "
          f"{trous_franchis} trou(s) franchi(s), dernier vivant : {dernier_vivant})")
    rc = bilan(conn, added_session, borne)
    conn.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
