"""Intègre le PCJA reconstruit (v2) : thesaurus.db + fichier publié.

CE QUE ÇA REMPLACE (30 août 2026)
─────────────────────────────────
`/var/www/justicelibre/data/pcja_reconstructed.json`, téléchargeable depuis
ressources.html et présenté comme l'unique version publique du Plan de
Classement de la Jurisprudence Administrative, contient **4 093 entrées
dont 3 526 (86 %) valent `<inconnu {code}>`**. Les mêmes chaînes peuplaient
`thesaurus.db` et partaient dans les requêtes FTS5 des utilisateurs comme
si c'étaient des synonymes.

La v2 (`reconstruct_pcja_v2.py`) nomme **6 293 concepts sur 6 437 (97,8 %)**,
et résout **100 %** des 3 526 codes que la v1 déclarait inconnus.

DEUX PRINCIPES
──────────────
1. **Plus jamais de `<inconnu>`.** Un concept sans nom sort avec
   `label: null` dans le fichier publié — c'est honnête, ça documente le
   trou — et il n'entre PAS dans `thesaurus_labels` : ce qui n'a pas de nom
   ne peut pas servir de synonyme.
2. **Le schéma publié ne change pas.** Mêmes clés qu'avant
   (code, label, parent, depth, freq_as_leaf, label_variants,
   freq_cumulative) : remplacement transparent pour qui a déjà écrit du
   code contre ce fichier.

Usage :
    python3 scripts/integrer_pcja_v2.py --source pcja_v2.json            # simulation
    python3 scripts/integrer_pcja_v2.py --source pcja_v2.json --apply    # écrit
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone

try:
    from unidecode import unidecode
except ImportError:                                    # pragma: no cover
    def unidecode(s):                                  # repli minimal
        import unicodedata
        s = unicodedata.normalize("NFD", s)
        return "".join(c for c in s if unicodedata.category(c) != "Mn")

DB_DEFAUT = "/opt/justicelibre/thesaurus/thesaurus.db"
PUBLIE_DEFAUT = "/var/www/justicelibre/data/pcja_reconstructed.json"
SOURCE = "pcja"
# Au-delà, ce n'est plus une rubrique mais un résumé d'affaire — cf. le
# commentaire de _est_rubrique dans reconstruct_pcja_v2.py.
LONGUEUR_MAX_LIBELLE = 100
SCOPE = "admin"


def normalise(s: str) -> str:
    """Même normalisation que thesaurus_engine.normalize — sinon l'index
    de recherche du moteur ne retrouverait pas les libellés insérés ici."""
    return unidecode(s).upper().strip()


def freq_cumulee(concepts: dict) -> dict[str, int]:
    """Fréquence propre + celle de toute la descendance."""
    enfants = defaultdict(list)
    for code, c in concepts.items():
        if c.get("parent"):
            enfants[c["parent"]].append(code)
    memo: dict[str, int] = {}

    def calcul(code: str) -> int:
        if code in memo:
            return memo[code]
        total = concepts.get(code, {}).get("freq", 0) or 0
        for fils in enfants.get(code, []):
            total += calcul(fils)
        memo[code] = total
        return total

    for code in concepts:
        calcul(code)
    return memo


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, help="JSON produit par reconstruct_pcja_v2.py")
    p.add_argument("--db", default=DB_DEFAUT)
    p.add_argument("--publie", default=PUBLIE_DEFAUT)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    with open(args.source, encoding="utf-8") as f:
        v2 = json.load(f)

    nommes = {k: v for k, v in v2.items() if v.get("label")}
    sans_nom = len(v2) - len(nommes)
    cumul = freq_cumulee(v2)

    print(f"source            : {args.source}")
    print(f"concepts          : {len(v2)}")
    print(f"  nommés          : {len(nommes)} ({100.0*len(nommes)/len(v2):.1f} %)")
    print(f"  sans nom        : {sans_nom}  → label:null, exclus du moteur")

    # ── Fichier publié, schéma d'origine ────────────────────────────────
    publie = {}
    for code, c in sorted(v2.items(), key=lambda kv: (kv[1]["depth"], kv[0])):
        publie[code] = {
            "code": code,
            "label": c.get("label"),          # null si inconnu, plus jamais "<inconnu …>"
            "parent": c.get("parent"),
            "depth": c.get("depth"),
            "freq_as_leaf": c.get("freq", 0),
            "label_variants": c.get("variantes", {}),
            "freq_cumulative": cumul.get(code, 0),
            # Champ de confiance, exigé par l'audit du 30 août 2026 : 28 %
            # des codes ne sont pas vérifiables contre la source. Publier
            # l'ensemble au même niveau de certitude serait trompeur pour un
            # fichier présenté comme l'unique reconstruction publique du PCJA.
            "confiance": c.get("confiance"),
            "attestations": c.get("attestations", 0),
        }
    inconnus_restants = sum(1 for v in publie.values()
                            if isinstance(v["label"], str) and v["label"].startswith("<"))

    # ── Lignes du thésaurus ─────────────────────────────────────────────
    concepts_rows, labels_rows, rel_rows = [], [], []
    vus_labels = set()
    for code, c in nommes.items():
        pref = c["label"]
        concepts_rows.append((SOURCE, code, pref, c.get("parent"), c["depth"], SCOPE,
                              c.get("freq", 0)))
        cle = (SOURCE, code, normalise(pref), "pref")
        if cle not in vus_labels:
            vus_labels.add(cle)
            labels_rows.append((SOURCE, code, pref, normalise(pref), "pref"))
        for variante in (c.get("variantes") or {}):
            if variante == pref:
                continue
            # Ceinture et bretelles : même si la reconstruction laissait
            # passer un résumé d'affaire, il n'entre pas comme synonyme.
            if len(variante) > LONGUEUR_MAX_LIBELLE:
                continue
            cle = (SOURCE, code, normalise(variante), "alt")
            if cle in vus_labels:
                continue
            vus_labels.add(cle)
            labels_rows.append((SOURCE, code, variante, normalise(variante), "alt"))
        if c.get("parent"):
            rel_rows.append((SOURCE, code, c["parent"], "broader"))

    print(f"\nà écrire en base  : {len(concepts_rows)} concepts, "
          f"{len(labels_rows)} libellés, {len(rel_rows)} relations")
    print(f"fichier publié    : {len(publie)} entrées, "
          f"{inconnus_restants} restées en « <inconnu > » (doit valoir 0)")

    if inconnus_restants:
        print("⛔ des marqueurs <inconnu> subsistent — on n'écrit pas.")
        return 3

    if not args.apply:
        print("\n⚠️  SIMULATION — rien n'a été écrit. Relancer avec --apply.")
        print("\nAperçu du fichier publié (5 entrées) :")
        for code in list(publie)[:5]:
            e = publie[code]
            print(f"  {code:14s} → {e['label']}  (niveau {e['depth']}, "
                  f"{e['freq_cumulative']} décisions)")
        return 0

    horo = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    # Sauvegardes AVANT toute écriture, sans exception.
    for chemin in (args.db, args.publie):
        if os.path.exists(chemin):
            sauve = f"{chemin}.bak_{horo}"
            shutil.copy2(chemin, sauve)
            print(f"sauvegarde : {sauve}")

    conn = sqlite3.connect(args.db, timeout=120.0)
    try:
        for table in ("thesaurus_labels", "thesaurus_relations", "thesaurus_concepts"):
            n = conn.execute(f"DELETE FROM {table} WHERE source = ?", (SOURCE,)).rowcount
            print(f"  purge {table:22s} : {n} lignes")
        conn.executemany(
            "INSERT INTO thesaurus_concepts (source, code, label, parent_code, depth, scope, freq)"
            " VALUES (?,?,?,?,?,?,?)", concepts_rows)
        conn.executemany(
            "INSERT INTO thesaurus_labels (source, code, label, label_normalized, label_type)"
            " VALUES (?,?,?,?,?)", labels_rows)
        conn.executemany(
            "INSERT INTO thesaurus_relations (source, src_code, dst_code, rel_type)"
            " VALUES (?,?,?,?)", rel_rows)
        conn.commit()
    finally:
        conn.close()

    tmp = f"{args.publie}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(publie, f, ensure_ascii=False, indent=1)
    os.replace(tmp, args.publie)

    # ── Contrôle après écriture ─────────────────────────────────────────
    ro = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    n_c = ro.execute("SELECT COUNT(*) FROM thesaurus_concepts WHERE source=?", (SOURCE,)).fetchone()[0]
    n_l = ro.execute("SELECT COUNT(*) FROM thesaurus_labels WHERE source=?", (SOURCE,)).fetchone()[0]
    reste = ro.execute("SELECT COUNT(*) FROM thesaurus_labels WHERE label LIKE '<%>'").fetchone()[0]
    ro.close()
    print(f"\ncontrôle base     : {n_c} concepts, {n_l} libellés, "
          f"{reste} marqueurs <inconnu> restants (toutes sources)")
    print(f"contrôle publié   : {os.path.getsize(args.publie)} octets")
    return 0 if reste == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
