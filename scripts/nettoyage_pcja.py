"""Nettoyage final du PCJA reconstruit + champ de confiance.

CE QUE CORRIGE CE SCRIPT (30 août 2026)
───────────────────────────────────────
Un arbitrage à l'aveugle a validé la reconstruction (5,8 % de libellés faux
contre 18,6 % pour la version en production, 12,7 citations gagnées pour 1
perdue) mais a listé six défauts résiduels, tous mécaniquement détectables.
Ils sont traités ici, dans l'ordre de gravité qu'il a établi :

1. CONTAMINATION par du texte de décision ou un titre d'analyse. Frappe des
   codes très visibles et peu profonds. Exemple mesuré, code `16` (6 042
   citations) : « Depuis la promulgation de la loi du 5 avril 1884, le
   ministre de l'intérieur est-il compétent pour statuer… » au lieu de
   « COMMUNE ».
2. La BRANCHE 16 (Commune) à elle seule pesait 67 % du poids perdu : six
   têtes de niveau 2 cassées, que l'ancienne version nommait correctement.
   Le repli corrige.
3. Le déchet « nég », artefact d'extraction, sur 6 codes.
4. 52 absences évitables (la source les nomme).
5. Le complément repris de l'ancienne version : 11,8 % d'erreur, et
   invérifiable à 77 %. On le garde — il apporte 246 bons libellés sur 279
   vérifiables — mais on le MARQUE.
6. 36 libellés tronqués finissant sur une abréviation ou un mot-outil.

LE CHAMP DE CONFIANCE, NON NÉGOCIABLE
─────────────────────────────────────
28,1 % des codes ne sont pas vérifiables contre la source. Publier
l'ensemble au même niveau de certitude serait trompeur — d'autant que ce
fichier est présenté comme la seule reconstruction publique du PCJA, et
fera donc autorité par défaut. Chaque entrée porte désormais :

    "confiance": "elevee"   nom issu de la forme moderne, auto-validée
                 "moyenne"  nom obtenu par réalignement de la forme ancienne
                 "faible"   repris de la version antérieure, non revérifié
                 null       pas de nom

Usage :
    python3 scripts/nettoyage_pcja.py --entree pcja_final_v5.json \\
        --repli pcja_v2.json --json pcja_publie.json
"""
import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict

LONGUEUR_SUSPECTE = 120
# Mots-outils et abréviations sur lesquels un nom de rubrique ne finit jamais.
FIN_TRONQUEE = re.compile(
    r"(?:\b(?:de|du|des|le|la|les|et|ou|à|au|aux|en|par|pour|sur|dans|un|une"
    r"|ce|cet|cette|art|n°|al)\s*[.\-]?|\b[A-Z]\.|\bL\.|\bR\.|\bD\.)$",
    re.IGNORECASE)
# Texte de décision : commence en minuscule, ou par une ponctuation, ou
# contient une tournure interrogative/conjuguée caractéristique.
DEBUT_SUSPECT = re.compile(r"^[a-zà-ÿ(\[«.,;:\-–—]")
PROSE = re.compile(r"\b(?:est-il|sont-ils|il résulte|considérant|attendu que"
                   r"|depuis la promulgation|en l'espèce|dès lors que)\b",
                   re.IGNORECASE)
DECHETS = {"NEG", "NÉG", "N/A", "IDEM", "ID"}
CODE_INTERNE = re.compile(r"\b\d{2,3}(?:-\d{1,3}){2,}\b")
MARQUEURS_TITRE = re.compile(r"\b[1-9]\)\s|\[RJ|,RJ|\bRJ[123]\b|–|—|«|»|\s{4,}")


def _pli(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).upper().strip(" .,;:-–—")


def ancetres(code: str) -> list[str]:
    p = code.split("-")
    return ["-".join(p[: i + 1]) for i in range(len(p) - 1)]


def contamine(label: str) -> str | None:
    """Renvoie le motif de rejet, ou None si le libellé est acceptable."""
    if not label or len(label.strip()) < 2:
        return "vide"
    if _pli(label) in DECHETS:
        return "déchet d'extraction"
    if PROSE.search(label):
        return "texte de décision"
    if DEBUT_SUSPECT.match(label):
        return "début en minuscule ou ponctuation"
    if len(label) > LONGUEUR_SUSPECTE:
        return "trop long (titre d'analyse)"
    if CODE_INTERNE.search(label):
        return "code PCJA à l'intérieur"
    if MARQUEURS_TITRE.search(label):
        return "marqueur de titre"
    if FIN_TRONQUEE.search(label.strip()):
        return "fin tronquée"
    # Parenthèses ou crochets déséquilibrés : on a coupé au milieu d'une
    # référence. Exemple survivant au premier passage, code 16-06 :
    # « R.372-9 du code des communes] - ».
    if (label.count("(") != label.count(")")
            or label.count("[") != label.count("]")):
        return "parenthèse déséquilibrée"
    # Commence par une référence d'article : c'est un fragment de citation,
    # jamais un nom de rubrique.
    if re.match(r"^[LRD]\.?\s?\d", label.strip()):
        return "fragment de référence d'article"
    if label.strip().endswith(("-", "–", "—", ",", ";", ":")):
        return "fin sur une ponctuation"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entree", required=True)
    ap.add_argument("--repli", required=True, help="version antérieure, pour le repli")
    ap.add_argument("--json")
    args = ap.parse_args()

    d = json.load(open(args.entree, encoding="utf-8"))
    repli = json.load(open(args.repli, encoding="utf-8"))

    motifs: Counter = Counter()
    rejetes: list[str] = []
    for code, e in d.items():
        lab = e.get("label")
        if not lab:
            continue
        m = contamine(lab)
        if m:
            motifs[m] += 1
            rejetes.append(code)
            e["label"] = None
            e["origine"] = None
            e["_rejet"] = m

    # Repli contrôlé sur la version antérieure, pour les codes qu'on vient de
    # vider — c'est ce qui répare la branche 16, où l'ancienne version était
    # juste et la nouvelle contaminée.
    freres: dict[str, set[str]] = defaultdict(set)
    for e in d.values():
        if e.get("label") and e.get("parent"):
            freres[e["parent"]].add(_pli(e["label"]))

    repris = 0
    for code in sorted(rejetes, key=lambda c: len(c.split("-"))):
        e = d[code]
        cand = (repli.get(code) or {}).get("label")
        if not cand or contamine(cand):
            continue
        p = _pli(cand)
        if any(_pli((d.get(a) or {}).get("label")) == p for a in ancetres(code)):
            continue
        if e.get("parent") and p in freres[e["parent"]]:
            continue
        e["label"] = cand
        e["origine"] = "v2"
        repris += 1
        if e.get("parent"):
            freres[e["parent"]].add(p)

    # ── Les VARIANTES aussi ─────────────────────────────────────────────
    # Elles entrent dans le moteur comme SYNONYMES : une variante sale y est
    # aussi nuisible qu'un libellé sale, en plus discret. Mesuré après la
    # première intégration : 913 variantes finissaient par un tiret orphelin
    # (« ACTES LEGISLATIFS - »), 151 commençaient par une minuscule ou une
    # ponctuation. Une telle chaîne, mise entre guillemets dans une requête
    # FTS5, ne peut rien trouver.
    nettoyees = supprimees = 0
    for e in d.values():
        var = e.get("variantes") or {}
        if not var:
            continue
        propre = {}
        for v, n in var.items():
            v2 = v.strip(" .,;:-–—\t")
            if not v2 or contamine(v2):
                supprimees += 1
                continue
            if v2 != v:
                nettoyees += 1
            propre[v2] = propre.get(v2, 0) + n
        e["variantes"] = propre
    print(f"variantes : {nettoyees} rognées, {supprimees} supprimées")

    # Champ de confiance, par entrée.
    for e in d.values():
        e.pop("_rejet", None)
        if not e.get("label"):
            e["confiance"] = None
        elif e.get("origine") == "v2":
            e["confiance"] = "faible"
        elif (e.get("attestations") or 0) >= 10:
            e["confiance"] = "elevee"
        else:
            e["confiance"] = "moyenne"

    nommes = sum(1 for e in d.values() if e.get("label"))
    conf = Counter(e.get("confiance") for e in d.values())
    print(f"concepts            : {len(d)}")
    print(f"  nommés            : {nommes} ({100.0*nommes/len(d):.1f} %)")
    print(f"  sans nom          : {len(d)-nommes}")
    print(f"\nlibellés rejetés    : {len(rejetes)}")
    for m, n in motifs.most_common():
        print(f"  {m:34s} : {n}")
    print(f"  → repris de la version antérieure : {repris}")
    print("\nconfiance :")
    for c in ("elevee", "moyenne", "faible", None):
        print(f"  {str(c):10s} : {conf.get(c, 0)}")

    par_parent = defaultdict(list)
    for e in d.values():
        if e.get("label") and e.get("parent"):
            par_parent[e["parent"]].append(e["label"])
    f_hom = sum(1 for labs in par_parent.values()
                for _, n in Counter(_pli(x) for x in labs).items() if n > 1)
    e_par = sum(1 for e in d.values()
                if e.get("label") and e.get("parent")
                and (d.get(e["parent"]) or {}).get("label")
                and _pli(e["label"]) == _pli(d[e["parent"]]["label"]))
    c_ded = sum(1 for e in d.values()
                if e.get("label") and CODE_INTERNE.search(e["label"]))
    longs = sum(1 for e in d.values() if e.get("label") and len(e["label"]) > 120)
    print("\nTESTS DE RECETTE   (version en production : 727 / 14 / 21 / 236)")
    for nom, v in (("codes en fratrie homonyme", f_hom), ("enfant = parent", e_par),
                   ("code PCJA dans le libellé", c_ded), ("libellé > 120 car.", longs)):
        print(f"  {'✓' if v == 0 else '·'} {nom:28s} : {v}")

    print("\névidence de contrôle (branche 16, la plus abîmée) :")
    for c in ("16", "16-02", "16-03", "16-06", "16-08", "55", "01-02"):
        e = d.get(c) or {}
        print(f"  {c:8s} → {str(e.get('label'))[:58]:58s} [{e.get('confiance')}]")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        print(f"\nécrit : {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
