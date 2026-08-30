"""Reconstruction du PCJA — v4, par le flux à séparateur POINT, auto-validé.

CE QUI A CONDUIT ICI (30 août 2026)
───────────────────────────────────
Trois tentatives ont échoué, chacune sur la même difficulté : dans la
convention d'écriture ANCIENNE, le tiret sépare les rubriques ET figure
DANS certains noms.

    01-04 = « VALIDITÉ DES ACTES ADMINISTRATIFS - VIOLATION DIRECTE DE LA
             RÈGLE DE DROIT »            ← UN nom, deux tirets
    55    = « PROFESSIONS - CHARGES ET OFFICES »

Découper sur ce tiret est indécidable. Les v1/v2 coupaient et décalaient
toute la descendance (216 fratries homonymes, 14 enfants portant le nom de
leur parent). La v3 a tenté la soustraction du parent : mesurée à 58 %
d'erreur contre 21 % pour la v2 — pire, parce qu'elle ne savait pas où
FINIT le niveau demandé (348 concaténations, 296 troncatures, 990 codes
laissés sans nom alors que la source les nomme).

LA SOLUTION EST DANS LA SOURCE, PAS DANS L'ALGORITHME
─────────────────────────────────────────────────────
Le Conseil d'État emploie DEUX conventions, et la moderne est NON AMBIGUË :

    tiret : 55-04-…-03 PROFESSIONS - CHARGES ET OFFICES - DISCIPLINE … - PHARMACIENS
    point : 19-04-02-01-04-082 Contributions et taxes. Impôts sur les revenus et
            bénéfices. Revenus et bénéfices imposables - règles particulières.
            Bénéfices industriels et commerciaux. Détermination du bénéfice net.
            Acte anormal de gestion.

Le point sépare ; le tiret reste à l'intérieur des noms. Et surtout, ce
flux **s'auto-valide** : le nombre de segments doit égaler la profondeur du
code. Sinon la ligne est rejetée — on n'infère rien, on s'abstient.

Aucun seuil, aucune heuristique, aucun arbitrage : soit la ligne se valide,
soit elle ne compte pas. Le nom retenu est la forme majoritaire parmi les
lignes validées.

COUVERTURE ATTENDUE
───────────────────
Mesuré indépendamment : 4 134 codes disposent d'au moins une ligne « point »,
3 115 en ont au moins deux. Les codes hors de ce flux restent `label: null` —
un trou déclaré vaut mieux qu'un nom faux mais plausible, qui ne se détecte
pas à l'usage.

Usage :
    python3 scripts/reconstruct_pcja_v4.py --json out.json
Ce script n'écrit JAMAIS dans thesaurus.db.
"""
import argparse
import json
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict

JADE_DEFAUT = "/opt/justicelibre/dila/jade.db"

# Nombre de décisions indépendantes exigé pour retenir un nom.
MIN_ATTESTATIONS = 2

MARQUEUR_BLOC = re.compile(r"\[[0-9A-Z]{1,6}(?:\s+[A-Z]+)?\]")
CODE_EN_TETE = re.compile(r"^\s*(\d{1,3}(?:-\d{1,3}){0,7})(?:,RJ\d+)?\s+(.*)$", re.S)
# Séparateur de niveau : un point suivi d'une espace puis d'une lettre.
SEP_POINT = re.compile(r"\.\s+(?=[A-Za-zÀ-ÿ])")
# Le titre d'analyse s'ouvre sur « . - », « - » entouré d'espaces, ou un
# tiret collé au mot suivant.
DEBUT_TITRE = re.compile(r"\.\s*-\s|\s-\s|\s-(?=\S)")


def profondeur(code: str) -> int:
    return len(code.split("-"))


def ancetres(code: str) -> list[str]:
    p = code.split("-")
    return ["-".join(p[: i + 1]) for i in range(len(p))]


def _pli(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).upper().strip(" .,;:-–—")


def blocs(texte: str):
    if not texte:
        return
    for morceau in MARQUEUR_BLOC.split(texte):
        for ligne in morceau.split("\n"):
            ligne = ligne.strip()
            if not ligne:
                continue
            m = CODE_EN_TETE.match(ligne)
            if m:
                yield m.group(1), m.group(2)


def segments_point(reste: str, attendu: int) -> list[str] | None:
    """Découpe une ligne « point » en niveaux, ou None si elle ne se valide pas.

    L'AUTO-VALIDATION est tout l'intérêt de ce flux : on n'accepte le
    découpage que si le nombre de segments est EXACTEMENT la profondeur du
    code. Une ligne qui ne tombe pas juste est écartée sans autre forme de
    procès — c'est ce qui rend la méthode fiable sans réglage.
    """
    m = DEBUT_TITRE.search(reste)
    hier = reste[: m.start()] if m else reste
    hier = hier.strip()
    if not hier:
        return None
    parts = [p.strip(" .;") for p in SEP_POINT.split(hier)]
    parts = [p for p in parts if p]
    if len(parts) != attendu:
        return None
    if any(len(p) < 2 for p in parts):
        return None
    return parts


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=JADE_DEFAUT)
    p.add_argument("--json")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    sql = ("SELECT sommaire, abstrats FROM jade_decisions "
           "WHERE (sommaire IS NOT NULL AND length(sommaire) > 30) "
           "   OR (abstrats IS NOT NULL AND length(abstrats) > 30)")
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"

    # code → Counter des noms de SON niveau, issus de lignes validées
    noms: dict[str, Counter] = defaultdict(Counter)
    freq: Counter = Counter()
    n_dec = n_lignes = n_valides = 0

    print("[pcja-v4] lecture, flux « point » auto-validé…", flush=True)
    for sommaire, abstrats in conn.execute(sql):
        n_dec += 1
        for texte in (abstrats, sommaire):
            for code, reste in blocs(texte or ""):
                n_lignes += 1
                freq[code] += 1
                prof = profondeur(code)
                parts = segments_point(reste, prof)
                if parts is None:
                    continue
                n_valides += 1
                # Une ligne validée nomme le code ET tous ses ancêtres :
                # c'est une chaîne complète, chaque segment à sa place.
                for a, nom in zip(ancetres(code), parts):
                    noms[a][nom] += 1
        if n_dec % 50000 == 0:
            print(f"  {n_dec} décisions, {n_valides}/{n_lignes} lignes validées, "
                  f"{len(noms)} codes nommés", flush=True)
    conn.close()

    tous: set[str] = set()
    for c in freq:
        tous.update(ancetres(c))
    tous.update(noms)

    concepts = {}
    for code in sorted(tous, key=lambda c: (profondeur(c), c)):
        cnt = noms.get(code)
        # ⚠️ Une seule attestation ne suffit pas. L'auto-validation par le
        # comptage des segments est nécessaire mais pas suffisante : une
        # ligne de prose peut compter juste par hasard. Mesuré sur 80 000
        # décisions — « 01-04-04 » recevait « Si le fait de ne pas y déférer
        # dans le délai d'un mois… », attesté 1 fois. Exiger DEUX décisions
        # indépendantes élimine ces coïncidences sans rien coûter d'autre :
        # 3 259 codes sur 3 634 franchissaient déjà ce seuil.
        label = None
        if cnt:
            candidat, n = cnt.most_common(1)[0]
            if n >= MIN_ATTESTATIONS:
                label = candidat
        parts = code.split("-")
        concepts[code] = {
            "code": code,
            "label": label,
            "parent": "-".join(parts[:-1]) if len(parts) > 1 else None,
            "depth": len(parts),
            "freq": freq.get(code, 0),
            "attestations": sum(cnt.values()) if cnt else 0,
            "variantes": dict(cnt.most_common(5)) if cnt else {},
        }

    nommes = sum(1 for c in concepts.values() if c["label"])
    solides = sum(1 for c in concepts.values() if c["attestations"] >= 2)
    print(f"\ndécisions lues      : {n_dec}")
    print(f"lignes d'analyse    : {n_lignes}")
    print(f"  dont validées     : {n_valides} ({100.0*n_valides/max(1,n_lignes):.1f} %)")
    print(f"concepts            : {len(concepts)}")
    print(f"  nommés            : {nommes} ({100.0*nommes/max(1,len(concepts)):.1f} %)")
    print(f"  attestés ≥ 2 fois : {solides}")
    print(f"  sans nom          : {len(concepts)-nommes}")

    # ── Tests de recette ────────────────────────────────────────────────
    par_parent = defaultdict(list)
    for c in concepts.values():
        if c["label"] and c["parent"]:
            par_parent[c["parent"]].append(c["label"])
    freres = sum(1 for labs in par_parent.values()
                 for _, n in Counter(_pli(x) for x in labs).items() if n > 1)
    enfant_parent = sum(
        1 for c in concepts.values()
        if c["label"] and c["parent"] and concepts.get(c["parent"], {}).get("label")
        and _pli(c["label"]) == _pli(concepts[c["parent"]]["label"]))
    codes_dedans = sum(1 for c in concepts.values()
                       if c["label"] and re.search(r"\b\d{2,3}(?:-\d{1,3}){2,}\b", c["label"]))
    print("\nTESTS DE RECETTE          (v2 en production : 216 / 14 / 3)")
    for nom_test, v in (("fratries homonymes", freres),
                        ("enfant = parent", enfant_parent),
                        ("code PCJA dans le libellé", codes_dedans)):
        print(f"  {'✓' if v == 0 else '✗'} {nom_test:28s} : {v}")

    print("\névidence de contrôle :")
    for c in ("01-04", "01-04-04", "55", "55-02", "36-05-04-01",
              "60-04-01-03-01", "19-04-02-05-03", "37-04-04-02"):
        e = concepts.get(c)
        lab = e["label"] if e and e["label"] else "(sans nom)"
        att = f"  [{e['attestations']}×]" if e and e["attestations"] else ""
        print(f"  {c:18s} → {lab[:66]}{att}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(concepts, f, ensure_ascii=False, indent=1)
        print(f"\nécrit : {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
