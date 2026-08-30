"""Reconstruction du PCJA — version 2, tolérante aux formats réels de JADE.

POURQUOI UNE V2 (30 août 2026)
──────────────────────────────
La v1 (`reconstruct_pcja.py`) a produit un thésaurus dont **3 526 étiquettes
sur 4 582 (77 %) valent `<inconnu {code}>`** — un pense-bête destiné à un
lecteur humain, qui est ensuite parti dans les requêtes FTS5 des
utilisateurs comme s'il s'agissait de synonymes.

Cause, vérifiée en faisant tourner la v1 sur les textes concernés : son
`HEADER_RE` exige une mise en forme unique — code, libellé en majuscules,
puis obligatoirement un espace suivi d'un mot en minuscules. Sur

    37-04-04-02 JURIDICTIONS … - GREFFIERS -Indemnité de suppression…

le motif ne colle pas (après GREFFIERS vient un tiret, pas un mot en
minuscules) et **le bloc entier est jeté** : `extract_blocks` renvoie 0.
Le nom est pourtant là, en clair. Ce code désigne « GREFFIERS ».

QUATRE FORMATS OBSERVÉS dans les données
────────────────────────────────────────
    [8AA PRINCIPAL] 01-03-02-06 ACTES … - VALIDITE … - FORME - …    tirets
    [8A PRINCIPAL]  54-01-05 PROCÉDURE. INTRODUCTION … . QUALITÉ…    points
    [8AA PRINCIPAL] - PROFESSIONS - CHARGES ET OFFICES. - ACCES …    sans code
    … \n [8BA PRINCIPAL] 54-03-015-04 …                              blocs multiples

Les séparateurs varient (` - `, `. - `, `. `) ET les libellés contiennent
des tirets internes (« PROFESSIONS - CHARGES ET OFFICES » est UN niveau).
Un séparateur unique ne peut pas trancher.

LA CLÉ : LE CODE DIT COMBIEN DE NIVEAUX ATTENDRE
────────────────────────────────────────────────
`01-03-02-06` a 4 segments, donc 4 niveaux de hiérarchie. On essaie
plusieurs découpages et on retient celui qui produit le bon compte. Ce
n'est pas une heuristique molle : c'est une contrainte vérifiable, fournie
par la donnée elle-même.

DEUX SOURCES, PAS UNE
─────────────────────
La v1 ne lisait que `sommaire` (302 848 décisions). `abstrats` en a
**328 329**. On lit les deux.

Usage :
    python3 scripts/reconstruct_pcja_v2.py                  # analyse seule
    python3 scripts/reconstruct_pcja_v2.py --json out.json  # écrit le résultat
Ce script n'écrit JAMAIS dans thesaurus.db — il produit un JSON qu'on
inspecte avant toute intégration.
"""
import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict

JADE_DEFAUT = "/opt/justicelibre/dila/jade.db"

# Marqueur de bloc : « [8AA PRINCIPAL] », « [800 PRINCIPAL] », « [9AA] »…
MARQUEUR = re.compile(r"\[[0-9A-Z]{1,6}(?:\s+[A-Z]+)?\]")

# Code PCJA en tête de bloc : 2 à 8 segments de 1 à 3 chiffres.
CODE = re.compile(r"^\s*(\d{1,3}(?:-\d{1,3}){0,7})\s+(.*)$", re.S)

# Découpages candidats, du plus spécifique au plus général. Chacun exige que
# le segment suivant commence par une majuscule (accentuée comprise) : un
# tiret suivi d'une minuscule introduit le résumé d'espèce, pas un niveau.
DECOUPAGES = (
    re.compile(r"\.\s*-\s*(?=[A-ZÀ-ÜŒÆ])"),      # « . - »
    re.compile(r"\s+-\s+(?=[A-ZÀ-ÜŒÆ])"),        # « - »
    re.compile(r"\.\s+(?=[A-ZÀ-ÜŒÆ])"),          # « . »
    re.compile(r"(?:\.\s*-\s*|\s+-\s+|\.\s+)(?=[A-ZÀ-ÜŒÆ])"),  # mixte
)


# Longueur maximale d'une rubrique de nomenclature (cf. _est_rubrique).
LONGUEUR_MAX_RUBRIQUE = 250
# La passe de SECOURS est plus tolérante — c'est son rôle — mais elle doit
# refuser une phrase. Sans ces bornes, 69 concepts se retrouvaient nommés
# par du texte d'arrêt : « La loi 81-1160 du 30 décembre 1981 a prévu à son
# article 23 que… » (356 caractères). Mesuré le 30 août 2026.
LONGUEUR_MAX_SECOURS = 250
PART_MAJUSCULES_SECOURS = 0.50
# En deçà, un libellé en casse normale reste acceptable : certaines vraies
# rubriques anciennes sont écrites ainsi (« Liberté du commerce et de
# l'industrie (voir : …) »). Au-delà, on exige une allure d'intitulé.
LONGUEUR_MAX_RUBRIQUE_COURTE = 120


def profondeur(code: str) -> int:
    return len(code.split("-"))


def ancetres(code: str) -> list[str]:
    p = code.split("-")
    return ["-".join(p[: i + 1]) for i in range(len(p))]


def _est_rubrique(seg: str) -> bool:
    """Une rubrique de nomenclature, ou un résumé d'espèce ?

    Le PCJA écrit ses rubriques en MAJUSCULES ; ce qui suit le dernier
    niveau — le résumé de l'affaire jugée — est en casse normale. Mesuré le
    30 août 2026 sur 200 codes : sans ce filtre, des résumés se hissaient
    au rang de nom de concept (« Illégalité du licenciement en rapport… »
    retenu pour 66-07-01-04-01, au lieu de « CONDITIONS DE FOND DE
    L'AUTORISATION »). On exige donc une majorité nette de majuscules.

    On tolère les chiffres, la ponctuation et les mots-outils courts en
    minuscules (« et », « de », « du », « des », « à », « ou »), qui
    figurent dans de vraies rubriques.
    """
    lettres = [c for c in seg if c.isalpha()]
    if len(lettres) < 3:
        return False
    # Une rubrique est COURTE. Un résumé d'affaire est long, et il est écrit
    # en majuscules lui aussi — le seul filtre de casse le laissait donc
    # passer. Constaté le 30 août 2026 après une première intégration : 127
    # concepts avaient pour nom principal un texte de plus de 200
    # caractères, du genre « GREFFIERS. - GREFFIERS DES TRIBUNAUX DE
    # COMMERCE - EXERCICE DU DROIT DE PRÉSENTATION - 1) DROIT ENFERMÉ… ».
    # Bornes observées : rubriques légitimes jusqu'à 93 caractères
    # (« CONVENTION EUROPEENNE DE SAUVEGARDE DES DROITS DE L'HOMME ET DES
    # LIBERTES FONDAMENTALES »), résumés à partir de 142. On coupe à 100.
    if len(seg) > LONGUEUR_MAX_RUBRIQUE:
        return False
    hautes = sum(1 for c in lettres if c.isupper())
    return hautes / len(lettres) >= 0.75


def _rubrique_plausible(seg: str) -> bool:
    """Contrôle allégé, pour la passe de SECOURS.

    Le secours doit rester tolérant — c'est sa raison d'être — mais il ne
    doit pas avaler une PHRASE. Sans ce contrôle, il nommait des concepts
    avec du texte d'arrêt en clair : « En renvoyant ainsi, pour la
    détermination des règles applicables au recouvrement… » (729
    caractères), « La loi 81-1160 du 30 décembre 1981 a prévu… » (356).
    Mesuré le 30 août 2026 : 181 noms dépassaient 100 caractères, dont la
    moitié étaient de la prose.

    On garde donc les libellés courts quelle que soit leur casse — certaines
    rubriques anciennes sont en casse normale, « Liberté du commerce et de
    l'industrie (voir : …) » en est une — mais dès qu'un segment s'allonge,
    on exige qu'il ressemble à un intitulé, pas à une phrase.
    """
    if len(seg) > LONGUEUR_MAX_SECOURS:
        return False
    lettres = [c for c in seg if c.isalpha()]
    if len(lettres) < 3:
        return False
    if len(seg) <= LONGUEUR_MAX_RUBRIQUE_COURTE:
        return True
    hautes = sum(1 for c in lettres if c.isupper())
    return hautes / len(lettres) >= PART_MAJUSCULES_SECOURS


def _nettoie(seg: str) -> str:
    """Retire la ponctuation résiduelle et le résumé d'espèce accolé."""
    seg = seg.strip().strip(" .-–—\t")
    # « GREFFIERS -Indemnité de suppression » → « GREFFIERS »
    seg = re.split(r"\s-(?=\S)", seg, maxsplit=1)[0]
    # « FORME ET PROCEDURE [art. 4 du décret] » → on garde tel quel : les
    # crochets font partie de certains libellés officiels.
    return seg.strip(" .-–—\t")


# Signatures d'un titre d'analyse, jamais d'une rubrique de nomenclature.
# Chacune mesurée sur un échantillon de 112 libellés classés à la main le
# 30 août 2026 : précision de 90 à 100 % selon le marqueur.
MARQUEURS_ANALYSE = re.compile(r"|".join((
    r"\b[1-9]\)\s",                 # énumération « 1) », « 2) »
    r"\b[AB]\)\s",                  # sous-énumération « a) », « b) »
    r"\[RJ|,RJ|\bRJ[123]\b",        # renvoi de jurisprudence
    r"–|—",                         # tirets demi-cadratin (format moderne)
    r"«|»",                         # guillemets
    r"\s{4,}",                      # colonnes de l'ancien format
)))

# Mots par lesquels le Conseil d'État conclut une analyse. Employés seuls,
# ce ne sont jamais des rubriques de nomenclature. Mesuré le 30 août 2026 :
# 184 concepts avaient pour nom entier l'un d'eux — dont 70 « EXISTENCE » et
# 70 « ABSENCE ». « OUI » et « NON » sont volontairement ABSENTS de la liste
# (« PROFESSIONS NON ORGANISEES EN ORDRES… » est une vraie rubrique).
MOTS_VERDICT = {
    "ABSENCE", "EXISTENCE", "INCLUSION", "EXCLUSION", "ILLUSTRATION",
    "CONSEQUENCE", "CONSÉQUENCE", "ILLEGALITE", "ILLÉGALITÉ",
    "IRREGULARITE", "IRRÉGULARITÉ",
}


def _porte_marqueur(seg: str) -> bool:
    """Le segment porte-t-il une signature de titre d'analyse ?"""
    if MARQUEURS_ANALYSE.search(seg):
        return True
    if seg.strip().upper().strip(" .-") in MOTS_VERDICT:
        return True
    if seg.count("(") != seg.count(")") or seg.count("[") != seg.count("]"):
        return True
    return False


def coupe_titre_analyse(reste: str) -> str:
    """Retire le titre d'analyse, ne garde que la chaîne hiérarchique.

    C'EST LA CORRECTION CENTRALE (30 août 2026). Le PCJA écrit d'abord la
    hiérarchie en capitales, puis le titre de l'analyse — lui aussi en
    capitales dans le format moderne. Sans cette coupe, quand la hiérarchie
    compte MOINS de segments que le code n'a de niveaux, le découpage
    déborde et affecte des morceaux du titre aux niveaux profonds.

    Conséquence mesurée avant correction : 70 codes nommés « EXISTENCE »,
    70 « ABSENCE », 184 concepts nommés par un simple mot-verdict. Un seuil
    de longueur n'y pouvait rien : « ABSENCE » fait sept caractères.

        format ancien   : « … - GREFFIERS -Indemnité de suppression… »
                          → le titre commence au tiret NON précédé d'espace
        format moderne  : « PROCÉDURE. … MOYEN PROPRE À CRÉER UN DOUTE. -
                            POSSIBILITÉ DE SUBORDONNER… »
                          → le titre commence au premier « . - » ou « - »
                            qui suit une chaîne à séparateurs « . »
    """
    # Format ancien : tiret collé au mot suivant.
    m = re.search(r"\s-(?=\S)", reste)
    coupe = m.start() if m else len(reste)
    # Format moderne : la chaîne est séparée par des points ; le premier
    # « - » entouré d'espaces ouvre alors le titre d'analyse.
    if re.search(r"\.\s+[A-ZÀ-ÜŒÆ]", reste[:coupe]):
        m2 = re.search(r"\.\s*-\s|\s-\s", reste[:coupe])
        if m2:
            coupe = m2.start()
    return reste[:coupe].strip()


def niveaux(reste: str, attendu: int, strict: bool = True) -> list[str] | None:
    """Découpe `reste` en `attendu` niveaux, ou None si aucun découpage ne colle.

    On accepte un découpage qui produit AU MOINS le nombre attendu : le
    surplus est le résumé de l'espèce, qu'on laisse tomber. On refuse un
    découpage qui en produit moins — mieux vaut ne rien nommer que nommer
    un niveau avec le libellé d'un autre.
    """
    hierarchie = coupe_titre_analyse(reste)
    if not hierarchie:
        return None
    meilleur: list[str] | None = None
    for motif in DECOUPAGES:
        parts = [_nettoie(p) for p in motif.split(hierarchie)]
        parts = [p for p in parts
                 if len(p) >= 2 and not p.isdigit()
                 and not _porte_marqueur(p)
                 and (_est_rubrique(p) if strict else _rubrique_plausible(p))]
        if not parts:
            continue
        # ⚠️ On ne comble JAMAIS un niveau manquant. Si la hiérarchie compte
        # moins de segments que le code n'a de niveaux, on nomme ce qu'on a
        # et on laisse le reste sans nom — c'est ainsi qu'on évite
        # d'attribuer un morceau de titre d'analyse à un niveau profond.
        candidat = parts[:attendu]
        if len(parts) == attendu:
            return candidat
        if meilleur is None or len(candidat) > len(meilleur):
            meilleur = candidat
    return meilleur


def blocs(texte: str):
    """Yield (code, reste) pour chaque bloc d'analyse du texte."""
    if not texte:
        return
    for morceau in MARQUEUR.split(texte):
        for ligne in morceau.split("\n"):
            ligne = ligne.strip()
            if not ligne:
                continue
            m = CODE.match(ligne)
            if not m:
                continue  # bloc sans code (format « - CONTRIBUTIONS ET TAXES »)
            yield m.group(1), m.group(2)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=JADE_DEFAUT)
    p.add_argument("--json", help="fichier de sortie (sinon : analyse seule)")
    p.add_argument("--limit", type=int, default=0, help="nb de décisions (0 = toutes)")
    args = p.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    sql = ("SELECT sommaire, abstrats FROM jade_decisions "
           "WHERE (sommaire IS NOT NULL AND length(sommaire) > 30) "
           "   OR (abstrats IS NOT NULL AND length(abstrats) > 30)")
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"

    # Deux récoltes. La STRICTE n'accepte qu'une rubrique en majuscules :
    # elle donne la forme canonique (87,9 % de noms identiques au texte
    # source, contre 77,8 % sans le filtre — mesuré le 30 août 2026). La
    # TOLÉRANTE prend tout : elle sert uniquement de secours pour les
    # concepts qu'aucune rubrique propre ne nomme, et récupère ainsi les
    # ~95 concepts que le filtre seul faisait perdre.
    libelles: dict[str, Counter] = defaultdict(Counter)
    secours: dict[str, Counter] = defaultdict(Counter)
    freq: Counter = Counter()
    n_dec = n_blocs = n_ok = n_ko = 0

    for sommaire, abstrats in conn.execute(sql):
        n_dec += 1
        for texte in (abstrats, sommaire):   # abstrats d'abord : meilleure couverture
            for code, reste in blocs(texte or ""):
                n_blocs += 1
                freq[code] += 1
                anc = ancetres(code)
                noms = niveaux(reste, len(anc), strict=True)
                if noms:
                    n_ok += 1
                    # zip s'arrête au plus court : les niveaux que la
                    # hiérarchie ne nomme pas restent simplement sans nom.
                    for a, nom in zip(anc, noms):
                        libelles[a][nom] += 1
                    continue
                n_ko += 1
                laches = niveaux(reste, len(anc), strict=False)
                if laches:
                    for a, nom in zip(anc, laches):
                        secours[a][nom] += 1
        if n_dec % 50000 == 0:
            print(f"  {n_dec} décisions, {n_blocs} blocs, {len(libelles)} concepts nommés",
                  flush=True)
    conn.close()

    # Tous les codes vus, ancêtres compris
    tous: set[str] = set()
    for c in set(freq) | set(libelles) | set(secours):
        tous.update(ancetres(c))

    concepts = {}
    nommes = par_secours = inconnus = 0
    for code in sorted(tous, key=lambda c: (c.count("-"), c)):
        cnt = libelles.get(code)
        origine = "rubrique"
        if not cnt:
            cnt = secours.get(code)
            origine = "secours"
        if cnt:
            nom = cnt.most_common(1)[0][0]
            nommes += 1
            if origine == "secours":
                par_secours += 1
        else:
            nom = None
            origine = None
            inconnus += 1
        parts = code.split("-")
        concepts[code] = {
            "code": code,
            "label": nom,
            "parent": "-".join(parts[:-1]) if len(parts) > 1 else None,
            "depth": len(parts),
            "freq": freq.get(code, 0),
            "origine": origine,
            "variantes": dict(cnt.most_common(3)) if cnt else {},
        }

    print(f"\ndécisions lues     : {n_dec}")
    print(f"blocs d'analyse    : {n_blocs}  ({n_ok} découpés, {n_ko} rejetés)")
    print(f"concepts au total  : {len(concepts)}")
    print(f"  nommés           : {nommes} ({100.0*nommes/max(1,len(concepts)):.1f} %)")
    print(f"    dont par rubrique stricte : {nommes - par_secours}")
    print(f"    dont par secours tolérant : {par_secours}")
    print(f"  sans nom         : {inconnus}")
    print("\névidence de contrôle (codes que la v1 n'a pas su nommer) :")
    for c in ("37-04-04-02", "01-01-01", "54-03-015-04", "19-04-02-01-04-04"):
        e = concepts.get(c)
        print(f"  {c:20s} → {(e['label'] if e and e['label'] else '*** toujours inconnu ***')[:80]}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(concepts, f, ensure_ascii=False, indent=1)
        print(f"\nécrit : {args.json}")
    else:
        print("\n(analyse seule — passer --json pour écrire le résultat)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
