#!/usr/bin/env python3
"""Compte le corpus réellement en base, une fois par nuit, pour que les chiffres
publiés (page /mcp-jurisprudence, et à terme accueil, README, llms.txt) viennent
d'une seule source et ne vieillissent plus (2 oct. 2026 : on lisait 3 M, 3,3 M
et 6,5 M selon les pages, et « 30 outils » pour 33).

Deux machines, deux modes :
  entrepot : compte les bases de l'entrepôt et écrit un JSON (poussé ensuite
             vers la prod par scp, l'entrepôt ayant la clé, pas l'inverse) ;
  prod     : compte judiciaire.db, fusionne le JSON de l'entrepôt, et écrit
             /var/www/justicelibre/corpus.json de façon atomique.

Les comptes sont des COUNT(*) en lecture seule (mesurés : 0,01 à 6 s par base).
Une base illisible n'est pas écrite à 0 : sa valeur est omise, et la page garde
son dernier chiffre connu. Un faux zéro publié serait pire qu'un chiffre daté.
"""
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone

DILA = "/opt/justicelibre/dila"

ENTREPOT = {
    "jade": ("jade.db", "jade_decisions"),
    "opendata": ("opendata.db", "opendata_decisions"),
    "legi": ("legi.db", "legi_articles"),
    "jorf": ("jorf.db", "jorf_textes"),
    "kali": ("kali.db", "kali_textes"),
    "cnil": ("cnil.db", "cnil_deliberations"),
    "doctrine": ("doctrine.db", "docs"),
}

PROD = {
    "judiciaire": "SELECT COUNT(*) FROM decisions WHERE juridiction <> 'Conseil constitutionnel'",
    "constit": "SELECT COUNT(*) FROM decisions WHERE juridiction = 'Conseil constitutionnel'",
    "cedh": "SELECT COUNT(*) FROM cedh_decisions",
    "cjue": "SELECT COUNT(*) FROM cjue_decisions",
    "ariane": "SELECT COUNT(*) FROM ariane_decisions",
}


def _count(db: str, sql: str):
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
        try:
            n = conn.execute(sql).fetchone()[0]
        finally:
            conn.close()
        return int(n) if n else None
    except Exception as e:
        print(f"[corpus] {db} : {type(e).__name__}: {e}", file=sys.stderr)
        return None


def _ecrire(path: str, data: dict) -> None:
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".corpus-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in ("entrepot", "prod"):
        print("usage : compte_corpus.py entrepot|prod <fichier.json>", file=sys.stderr)
        return 2
    mode, sortie = argv[1], argv[2]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if mode == "entrepot":
        fonds = {k: _count(f"{DILA}/{db}", f"SELECT COUNT(*) FROM {t}")
                 for k, (db, t) in ENTREPOT.items()}
        _ecrire(sortie, {"compte_le": now, "fonds": {k: v for k, v in fonds.items() if v}})
        print(f"[corpus] entrepôt : {fonds}")
        return 0 if all(fonds.values()) else 1

    # prod : bases locales + JSON poussé par l'entrepôt + dernier corpus publié
    fonds = {k: _count(f"{DILA}/judiciaire.db", sql) for k, sql in PROD.items()}
    entrepot = {}
    try:
        with open("/opt/justicelibre/data/corpus_entrepot.json") as f:
            entrepot = json.load(f).get("fonds", {})
    except Exception as e:
        print(f"[corpus] JSON entrepôt illisible : {e}", file=sys.stderr)
    precedent = {}
    try:
        with open(sortie) as f:
            precedent = json.load(f).get("fonds", {})
    except Exception:
        pass
    final = dict(precedent)
    final.update(entrepot)
    final.update({k: v for k, v in fonds.items() if v})
    # Nombre d'outils MCP réellement déclarés (un décorateur par outil).
    try:
        with open("/opt/justicelibre/server.py") as f:
            n = sum(1 for l in f if l.startswith("@mcp.tool"))
        if n:
            final["outils"] = n
    except Exception as e:
        print(f"[corpus] server.py illisible : {e}", file=sys.stderr)
    _ecrire(sortie, {"compte_le": now, "fonds": final})
    print(f"[corpus] publié : {final}")
    manquants = [k for k, v in fonds.items() if not v] + [k for k in ENTREPOT if k not in entrepot]
    return 1 if manquants else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
