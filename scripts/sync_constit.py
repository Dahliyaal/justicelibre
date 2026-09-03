"""Propage les décisions du Conseil constitutionnel vers la base servie.

LE TROU QUE ÇA BOUCHE (4 septembre 2026)
────────────────────────────────────────
Les deux machines ont chacune leur cron, et aucun ne parle à l'autre :

    al-uzza  04h00  dila_update_daily.sh   → met à jour constit.db
    prod     04h30  judilibre_sync_daily   → alimente decisions (Judilibre)

Or Judilibre ne diffuse PAS le Conseil constitutionnel : il couvre la Cour de
cassation, les cours d'appel, les tribunaux judiciaires et les tribunaux de
commerce. La table `decisions` que `search_cc` et `get_cc_decision`
interrogent a donc été remplie une fois, à l'import initial, puis plus jamais
pour ce fonds.

Constat du 4 septembre 2026 :

    constit.db (al-uzza, à jour)   7 379 décisions   jusqu'au 2026-07-03
    decisions  (prod, servie)      7 112 décisions   jusqu'au 2025-06-20

Quatorze mois de QPC et de DC — toute la saison 2025-2026 — répondaient
`total: 0` sans le moindre message. Un utilisateur cherchant une QPC de 2026
en concluait qu'elle n'existait pas.

⚠️ Ce n'est PAS la constante morte `CONSTIT_DB` (sources/dila.py:16) qui cause
le gel : elle désigne un chemin qui n'existe même pas sur la prod. C'est un
tuyau qui n'a jamais été posé. La constante morte est un défaut distinct.

OÙ ÇA TOURNE
────────────
Sur **al-uzza** (46.224.173.253), qui détient constit.db ET la clé ssh vers la
prod (l'inverse n'est pas vrai). Le script s'expédie lui-même sur la prod et
s'y rappelle en mode `--applier`, pour n'avoir qu'un seul fichier à déployer.

CE QU'IL FAIT, ET CE QU'IL NE FAIT PAS
──────────────────────────────────────
Il INSÈRE les décisions absentes, jamais rien d'autre. Pas de mise à jour des
lignes existantes, pas de suppression. Une décision republiée par DILA sous le
même identifiant ne sera donc pas rafraîchie : c'est une limite assumée de
cette version, le trou à boucher étant l'absence pure et simple.

Les trois déclencheurs FTS (`decisions_ai/ad/au`) sont en place sur la table :
l'index de recherche se met à jour tout seul à l'insertion. Rien à reconstruire.

Usage :
    python3 scripts/sync_constit.py              # essai à blanc, n'écrit rien
    python3 scripts/sync_constit.py --apply      # écrit
"""
import argparse
import gzip
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys

SOURCE_DB = "/opt/justicelibre/dila/constit.db"
CIBLE_DB = "/mnt/digesta/judiciaire.db"
PROD = "root@46.225.190.237"
JURIDICTION = "Conseil constitutionnel"

# Au-delà, ce n'est plus un rattrapage : c'est que quelque chose a changé de
# structure (base source remplacée, identifiants renumérotés). On refuse
# d'écrire et on demande un humain.
PLAFOND_RATTRAPAGE = 2000

DATE_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# constit_decisions → decisions. Seule différence de nom : texte → text.
# `avocat_general` n'existe pas dans la table cible : abandonné volontairement.
COLONNES = [
    ("id", "id"), ("ecli", "ecli"), ("juridiction", "juridiction"),
    ("formation", "formation"), ("date", "date"), ("numero", "numero"),
    ("solution", "solution"), ("nature", "nature"), ("president", "president"),
    ("rapporteur", "rapporteur"), ("avocats", "avocats"), ("titre", "titre"),
    ("sommaire", "sommaire"), ("texte", "text"), ("abstrats", "abstrats"),
    ("resume", "resume"), ("renvois", "renvois"),
    ("commissaire_gvt", "commissaire_gvt"), ("type_rec", "type_rec"),
    ("publi_recueil", "publi_recueil"), ("publi_bull", "publi_bull"),
    ("nature_qualifiee", "nature_qualifiee"), ("saisines", "saisines"),
    ("loi_def", "loi_def"), ("liens_textes", "liens_textes"),
]


def defauts(ligne: dict) -> list[str]:
    """Ce qui interdit d'insérer cette ligne. Vide = elle est bonne."""
    mauvais = []
    if not str(ligne.get("id") or "").startswith("CONSTEXT"):
        mauvais.append(f"identifiant inattendu : {ligne.get('id')!r}")
    if not DATE_ISO.match(str(ligne.get("date") or "")):
        mauvais.append(f"date non ISO : {ligne.get('date')!r}")
    if not (ligne.get("text") or "").strip():
        mauvais.append("texte vide")
    # Le filtre de search_cc est une égalité stricte sur ce libellé : une
    # variante d'orthographe rendrait la décision insérée mais introuvable.
    if ligne.get("juridiction") != JURIDICTION:
        mauvais.append(f"juridiction {ligne.get('juridiction')!r} ≠ {JURIDICTION!r}")
    return mauvais


# ── mode applier : s'exécute SUR la prod ────────────────────────────────────

def appliquer(chemin_ndjson: str, ecrire: bool) -> int:
    lignes = []
    with gzip.open(chemin_ndjson, "rt", encoding="utf-8") as f:
        for l in f:
            if l.strip():
                lignes.append(json.loads(l))

    conn = sqlite3.connect(CIBLE_DB, timeout=120.0)
    try:
        avant = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE juridiction = ?", (JURIDICTION,)
        ).fetchone()[0]
        print(f"cible avant        : {avant} décisions « {JURIDICTION} »")

        if not ecrire:
            print(f"⚠️  ESSAI À BLANC — {len(lignes)} lignes prêtes, rien écrit.")
            return 0

        cibles = [c for _, c in COLONNES]
        sql = (f"INSERT OR IGNORE INTO decisions ({', '.join(cibles)}) "
               f"VALUES ({', '.join('?' * len(cibles))})")
        conn.executemany(sql, [[l.get(c) for c in cibles] for l in lignes])
        conn.commit()

        apres = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE juridiction = ?", (JURIDICTION,)
        ).fetchone()[0]
        borne = conn.execute(
            "SELECT MAX(date) FROM decisions WHERE juridiction = ?", (JURIDICTION,)
        ).fetchone()[0]
        print(f"cible après        : {apres} (+{apres - avant}), jusqu'au {borne}")

        # Contrôle de l'index : une décision insérée doit être RETROUVABLE,
        # sinon on a rempli la table sans rien rendre cherchable.
        if lignes:
            temoin = lignes[-1]["id"]
            trouve = conn.execute(
                "SELECT COUNT(*) FROM decisions_fts f JOIN decisions d "
                "ON d.rowid = f.rowid WHERE f.decisions_fts MATCH ? AND d.id = ?",
                (f'"{temoin}"', temoin),
            ).fetchone()[0]
            etat = "✓ indexée" if trouve else "⛔ ABSENTE DE L'INDEX"
            print(f"contrôle FTS       : {temoin} → {etat}")
            if not trouve:
                return 4
        return 0
    finally:
        conn.close()


# ── mode normal : s'exécute sur al-uzza ─────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="écrit réellement")
    p.add_argument("--applier", metavar="NDJSON.GZ",
                   help="usage interne : mode d'application, sur la prod")
    p.add_argument("--source", default=SOURCE_DB)
    args = p.parse_args()

    if args.applier:
        return appliquer(args.applier, args.apply)

    src = sqlite3.connect(f"file:{args.source}?mode=ro", uri=True, timeout=60)
    src.row_factory = sqlite3.Row

    # Ce que la prod possède déjà. On demande les identifiants plutôt que la
    # date maximale : une décision ancienne publiée tardivement par DILA
    # passerait sous un simple critère de date.
    lecture = (
        "import sqlite3;"
        f"c=sqlite3.connect('file:{CIBLE_DB}?mode=ro',uri=True,timeout=120);"
        f"print('\\n'.join(r[0] for r in c.execute("
        f'"SELECT id FROM decisions WHERE juridiction=\'{JURIDICTION}\'")))'
    )
    out = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", PROD,
         f"python3 -c {shlex.quote(lecture)}"],
        capture_output=True, text=True, timeout=180)
    if out.returncode != 0:
        print(f"⛔ lecture de la prod impossible : {out.stderr.strip()[:300]}")
        return 2
    deja = {l.strip() for l in out.stdout.splitlines() if l.strip()}

    total_src = src.execute("SELECT COUNT(*) FROM constit_decisions").fetchone()[0]
    print(f"source (constit.db) : {total_src} décisions")
    print(f"cible (prod)        : {len(deja)} décisions")

    manquantes, rejetees = [], []
    champs = ", ".join(s for s, _ in COLONNES)
    for r in src.execute(f"SELECT {champs} FROM constit_decisions"):
        if r["id"] in deja:
            continue
        ligne = {cible: r[source] for source, cible in COLONNES}
        mauvais = defauts(ligne)
        (rejetees if mauvais else manquantes).append((ligne, mauvais))
    src.close()

    print(f"\nà insérer           : {len(manquantes)}")
    print(f"rejetées au contrôle : {len(rejetees)}")
    for ligne, mauvais in rejetees[:10]:
        print(f"   {str(ligne.get('id'))[:24]:26s} {'; '.join(mauvais)}")

    if not manquantes:
        print("\nRien à faire : la base servie est à jour.")
        return 0

    dates = sorted(l["date"] for l, _ in manquantes)
    print(f"période concernée   : {dates[0]} → {dates[-1]}")
    print("\naperçu (5 plus récentes) :")
    for ligne, _ in sorted(manquantes, key=lambda x: x[0]["date"], reverse=True)[:5]:
        print(f"   {ligne['date']}  {str(ligne['numero']):16s} {str(ligne['nature']):5s} "
              f"{str(ligne['titre'])[:46]}")

    if len(manquantes) > PLAFOND_RATTRAPAGE:
        print(f"\n⛔ {len(manquantes)} lignes à insérer, au-delà du plafond de "
              f"{PLAFOND_RATTRAPAGE}. Ce n'est plus un rattrapage courant : "
              f"vérifier à la main avant de forcer.")
        return 3

    if not args.apply:
        print("\n⚠️  ESSAI À BLANC — rien n'a été écrit. Relancer avec --apply.")
        return 0

    # Expédition : le script s'envoie lui-même, pour n'avoir qu'un fichier.
    lot = "/tmp/constit_a_inserer.ndjson.gz"
    with gzip.open(lot, "wt", encoding="utf-8") as f:
        for ligne, _ in manquantes:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    print(f"\nlot écrit : {lot} ({os.path.getsize(lot)} octets)")

    moi = os.path.abspath(__file__)
    for source, cible in ((lot, lot), (moi, "/tmp/sync_constit.py")):
        r = subprocess.run(["scp", "-q", "-o", "BatchMode=yes", source,
                            f"{PROD}:{cible}"], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"⛔ envoi de {source} impossible : {r.stderr.strip()[:200]}")
            return 2

    r = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", PROD,
         f"python3 /tmp/sync_constit.py --applier {lot} --apply"],
        capture_output=True, text=True, timeout=600)
    print(r.stdout.rstrip())
    if r.stderr.strip():
        print(r.stderr.strip()[:600], file=sys.stderr)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
