"""Reconstruction du PCJA — v3, par SOUSTRACTION DU PARENT.

POURQUOI UNE V3 (30 août 2026)
──────────────────────────────
Les v1 et v2 découpaient la chaîne de rubriques sur des séparateurs
(« - », « . - », « . »). C'est indécidable : **certains noms de rubrique
contiennent eux-mêmes un tiret**.

    01-04 = « VALIDITÉ DES ACTES ADMINISTRATIFS - VIOLATION DIRECTE DE LA
             RÈGLE DE DROIT »          ← UN seul nom, pas deux
    01-01-05 = « ACTES ADMINISTRATIFS - NOTION »
    66-07-01 = « AUTORISATION ADMINISTRATIVE - SALARIÉS PROTÉGÉS »

En coupant sur ce tiret, tout ce qui suit se décale d'un cran. Un audit à
l'aveugle du 30 août 2026 a mesuré les dégâts sur la v2 :

    ~700 codes portent le nom du MAUVAIS niveau (15,9 % de la masse
    documentaire) ; 203 groupes de codes FRÈRES portent un nom identique
    (16 enfants nommés « ARTICLES 34 ET 37 DE LA CONSTITUTION », 18
    nommés « MINISTRES ») ; 18 enfants portent le nom de leur parent.

Un nom faux mais plausible est plus nuisible qu'un nom absent : il ne se
détecte pas à l'usage.

LE PRINCIPE DE LA V3
────────────────────
On ne cherche plus OÙ couper. On RETRANCHE une chaîne connue :

    nom(C) = chaîne_canonique(C) − chaîne_canonique(parent(C))

et la chaîne canonique d'un code s'obtient par CONSENSUS de sa descendance :
le préfixe majoritaire, mot à mot, de toutes les chaînes observées pour ce
code et pour tous ses descendants. Un mot n'est retenu que s'il est écrit
par plus de la moitié des décisions à cette position.

Ce consensus absorbe trois difficultés d'un coup :
  - les séparateurs variables (« - », « . », « . - ») ;
  - les variantes typographiques (accents, doubles espaces, casse) ;
  - les renommages du Conseil d'État au fil du temps — c'est la forme
    majoritaire qui l'emporte, et les minoritaires restent dans
    `variantes`, publiées plutôt que cachées.

DEUX ERREURS DE LA V2 QUE LA V3 NE REFAIT PAS
─────────────────────────────────────────────
1. « ABSENCE » et « EXISTENCE » avaient été filtrés comme du bruit. Ce sont
   de VRAIES rubriques terminales du PCJA (« Caractère direct du préjudice
   — Absence »), attestées 352 fois sur 400 pour 60-04-01-03-01. Le filtre
   détruisait ~84 noms corrects. Il est supprimé.
2. Quand la chaîne compte moins de segments que le code n'a de niveaux, on
   NE COMBLE PAS : le niveau reste sans nom. `null` est une information,
   un nom inventé est un mensonge.

TESTS DE RECETTE (binaires, vérifiés en fin d'exécution)
────────────────────────────────────────────────────────
  - zéro groupe de frères homonymes      (v2 : 203 groupes, 700 codes)
  - zéro enfant homonyme de son parent   (v2 : 18)
  - zéro libellé contenant un code PCJA  (v2 : 17)

Usage :
    python3 scripts/reconstruct_pcja_v3.py --json out.json
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

MARQUEUR_BLOC = re.compile(r"\[[0-9A-Z]{1,6}(?:\s+[A-Z]+)?\]")
CODE_EN_TETE = re.compile(r"^\s*(\d{1,3}(?:-\d{1,3}){0,7})(?:,RJ\d+)?\s+(.*)$", re.S)
# Un code PCJA égaré DANS un libellé : signe qu'on a mordu sur le bloc suivant.
CODE_INTERNE = re.compile(r"\b\d{2,3}(?:-\d{1,3}){2,}\b")

# Part minimale d'accord pour retenir un mot dans le consensus.
CONSENSUS = 0.50
# Un code doit être vu au moins ce nombre de fois pour qu'on le nomme.
MIN_OCCURRENCES = 2


def profondeur(code: str) -> int:
    return len(code.split("-"))


def ancetres(code: str) -> list[str]:
    p = code.split("-")
    return ["-".join(p[: i + 1]) for i in range(len(p))]


def parent(code: str) -> str | None:
    p = code.split("-")
    return "-".join(p[:-1]) if len(p) > 1 else None


def _pli(mot: str) -> str:
    """Forme comparable : sans accent, sans casse, sans ponctuation de bord."""
    m = unicodedata.normalize("NFD", mot)
    m = "".join(c for c in m if unicodedata.category(c) != "Mn")
    return m.upper().strip(" .,;:-–—()[]«»\"'")


def coupe_titre_analyse(reste: str) -> str:
    """Ne garde que la chaîne de rubriques, sans le titre de l'analyse.

    Deux formes rédactionnelles, vérifiées sur les données :
      ancienne : « … - GREFFIERS -Indemnité de suppression… »
                 le titre s'ouvre sur un tiret COLLÉ au mot suivant ;
      moderne  : « PROCÉDURE. … MOYEN PROPRE À CRÉER UN DOUTE. - POSSIBILITÉ
                 DE SUBORDONNER… » — la chaîne est à points, et le premier
                 « - » entouré d'espaces ouvre le titre.
    """
    m = re.search(r"\s-(?=\S)", reste)
    fin = m.start() if m else len(reste)
    if re.search(r"\.\s+[A-ZÀ-ÜŒÆ]", reste[:fin]):
        m2 = re.search(r"\.\s*-\s|\s-\s", reste[:fin])
        if m2:
            fin = m2.start()
    return reste[:fin].strip()


def tokens_spans(chaine: str):
    """[(mot plié, début, fin)] — les positions permettent de restituer la
    ponctuation INTERNE d'un nom. Sans elles, « VALIDITÉ DES ACTES
    ADMINISTRATIFS - VIOLATION DIRECTE… » ressortait sans son tiret, alors
    que ce tiret fait partie du nom officiel de la rubrique."""
    out = []
    for m in re.finditer(r"\S+", chaine):
        p = _pli(m.group(0))
        if p and p not in ("-", "–", "—", "."):
            out.append((p, m.start(), m.end()))
    return out


def mots(chaine: str) -> list[str]:
    """Découpe en mots comparables, séparateurs de niveau compris.

    On ne cherche PAS à identifier les niveaux : on aligne mot à mot. Les
    séparateurs eux-mêmes sont écartés, si bien que « A - B » et « A. B »
    produisent la même séquence — c'est ce qui rend le consensus insensible
    à la ponctuation.
    """
    bruts = re.split(r"[\s]+", chaine)
    out = []
    for b in bruts:
        p = _pli(b)
        if p and p not in ("-", "–", "—", "."):
            out.append(p)
    return out


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


def consensus_prefixe(sequences: list[list[str]], formes: list[list[str]]) -> list[str]:
    """Préfixe majoritaire, mot à mot, avec restitution de la forme d'origine.

    `sequences` : les chaînes pliées (comparables).
    `formes`    : les mêmes chaînes en écriture d'origine, alignées.
    On avance tant qu'un mot rassemble plus de CONSENSUS des séquences
    encore en lice. C'est ce qui absorbe les variantes d'époque : la
    rédaction majoritaire gagne, les autres sont conservées ailleurs.
    """
    if not sequences:
        return []
    sortie: list[str] = []
    i = 0
    while True:
        candidats = [(s, f) for s, f in zip(sequences, formes) if len(s) > i]
        if not candidats:
            break
        compte = Counter(s[i] for s, _ in candidats)
        mot, n = compte.most_common(1)[0]
        if n / len(sequences) < CONSENSUS:
            break
        # Forme d'origine la plus fréquente pour ce mot à cette position
        ecritures = Counter(f[i] for s, f in candidats if s[i] == mot and len(f) > i)
        sortie.append(ecritures.most_common(1)[0][0] if ecritures else mot)
        i += 1
    return sortie


def _restitue(observations: list, debut: int, fin: int, attendus: list[str]) -> str | None:
    """Retrouve le texte d'origine des mots [debut, fin), ponctuation comprise.

    On cherche une chaîne réellement observée qui contient au moins `fin`
    mots, et on la tranche aux positions mémorisées. C'est ce qui rend
    « VALIDITÉ DES ACTES ADMINISTRATIFS - VIOLATION DIRECTE DE LA RÈGLE DE
    DROIT » à l'identique, tiret compris, au lieu d'un recollage à l'espace.
    """
    if fin <= debut:
        return None
    # ⚠️ Il ne suffit PAS qu'une observation soit assez longue : il faut que
    # ses mots soient CEUX qu'on a retenus. Sans ce contrôle, on tranchait
    # dans une chaîne quelconque et « 01-04-04 » ressortait « chose jugée
    # qui s'attache à la décision du Conseil d'Etat » — du texte d'arrêt,
    # en minuscules, aux bonnes positions mais dans la mauvaise décision.
    candidates = []
    for chaine, spans in observations:
        if len(spans) < fin:
            continue
        if [t[0] for t in spans[debut:fin]] != [_pli(m) for m in attendus]:
            continue
        txt = chaine[spans[debut][1]:spans[fin - 1][2]].strip(" .,;:-–—")
        if txt:
            candidates.append(txt)
    if not candidates:
        return None
    # La graphie la plus fréquente l'emporte (accents, casse, espaces).
    return Counter(candidates).most_common(1)[0][0]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=JADE_DEFAUT)
    p.add_argument("--json", help="fichier de sortie")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    sql = ("SELECT sommaire, abstrats FROM jade_decisions "
           "WHERE (sommaire IS NOT NULL AND length(sommaire) > 30) "
           "   OR (abstrats IS NOT NULL AND length(abstrats) > 30)")
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"

    # code → liste des chaînes observées (pliées + formes d'origine)
    chaines_plie: dict[str, list[list[str]]] = defaultdict(list)
    chaines_forme: dict[str, list[list[str]]] = defaultdict(list)
    brutes: dict[str, list] = defaultdict(list)   # (chaîne d'origine, spans)
    freq: Counter = Counter()
    n_dec = n_blocs = 0

    print("[pcja-v3] lecture des analyses…", flush=True)
    for sommaire, abstrats in conn.execute(sql):
        n_dec += 1
        for texte in (abstrats, sommaire):
            for code, reste in blocs(texte or ""):
                hier = coupe_titre_analyse(reste)
                if not hier:
                    continue
                n_blocs += 1
                freq[code] += 1
                ts = tokens_spans(hier)
                if ts:
                    chaines_plie[code].append([t[0] for t in ts])
                    chaines_forme[code].append([hier[t[1]:t[2]] for t in ts])
                    brutes[code].append((hier, ts))
        if n_dec % 50000 == 0:
            print(f"  {n_dec} décisions, {n_blocs} blocs, {len(freq)} codes", flush=True)
    conn.close()

    # Tous les codes, ancêtres compris
    tous: set[str] = set()
    for c in freq:
        tous.update(ancetres(c))

    # ── Agrégation PONDÉRÉE PAR ENFANT, pas par occurrence ──────────────
    #
    # Premier essai (rejeté) : entasser toutes les chaînes de la descendance
    # et prendre le préfixe majoritaire. Une branche volumineuse écrase
    # alors les autres — le consensus de « 01 » avalait « VALIDITÉ DES
    # ACTES ADMINISTRATIFS », qui appartient à son enfant 01-04, parce que
    # ce sous-arbre pèse plus que tous les frères réunis. Le nom de 01-04
    # s'en trouvait amputé de sa première moitié.
    #
    # La chaîne d'un code doit être ce que TOUS ses enfants ont en commun,
    # chacun comptant pour UNE voix quel que soit son volume. On calcule
    # donc d'abord la chaîne propre de chaque code, puis on remonte des
    # feuilles vers la racine.
    print("[pcja-v3] agrégation pondérée par enfant…", flush=True)
    enfants: dict[str, list[str]] = defaultdict(list)
    for code in tous:
        par = parent(code)
        if par:
            enfants[par].append(code)

    propre_plie: dict[str, list[str]] = {}
    propre_forme: dict[str, list[str]] = {}
    for code, seqs in chaines_plie.items():
        c = consensus_prefixe(seqs, chaines_forme[code])
        if c:
            propre_forme[code] = c
            propre_plie[code] = [_pli(w) for w in c]

    agrege_plie: dict[str, list[str]] = {}
    agrege_forme: dict[str, list[str]] = {}
    for code in sorted(tous, key=lambda c: (-profondeur(c), c)):   # feuilles d'abord
        votes_p: list[list[str]] = []
        votes_f: list[list[str]] = []
        # Les observations PROPRES du code font foi : elles s'arrêtent
        # exactement à son niveau. On ne se sert de la descendance que
        # faute de mieux — et alors il faut AU MOINS DEUX enfants, sinon
        # le préfixe commun est la chaîne entière de l'enfant unique et le
        # parent hérite du nom de son fils (« 01-04-04 » ressortait
        # « CHOSE JUGEE CHOSE JUGEE PAR LE JUGE »).
        # La FRONTIÈRE d'un code, c'est là où ses enfants divergent : leurs
        # chaînes commencent toutes par la sienne, puis chacune part sur son
        # propre nom. Le préfixe commun à DEUX enfants au moins donne donc
        # exactement la chaîne du parent, ni plus ni moins.
        #
        # Les observations propres du code ne servent qu'à défaut : elles
        # s'arrêtent au bon niveau mais sont parfois rares ou tronquées, et
        # un parent trop court fait absorber PLUSIEURS niveaux à ses enfants
        # (« 19-04-02-05-03 » ressortait « REGLES PARTICULIERES - BENEFICES
        # NON COMMERCIAUX - ETABLISSEMENT DE L'IMPOT », trois noms empilés).
        fils = [k for k in enfants.get(code, []) if k in agrege_plie]
        if len(fils) >= 2:
            for k in fils:
                votes_p.append(agrege_plie[k])
                votes_f.append(agrege_forme[k])
        elif code in propre_plie:
            votes_p.append(propre_plie[code])
            votes_f.append(propre_forme[code])
        if votes_p:
            c = consensus_prefixe(votes_p, votes_f)
            agrege_forme[code] = c
            agrege_plie[code] = [_pli(w) for w in c]

    desc_plie = {k: [v] for k, v in agrege_plie.items()}
    desc_forme = {k: [v] for k, v in agrege_forme.items()}

    # Résolution TOP-DOWN : le nom d'un code est ce que sa chaîne canonique
    # ajoute à celle de son parent.
    print("[pcja-v3] consensus et soustraction…", flush=True)
    canon: dict[str, list[str]] = {}
    concepts: dict[str, dict] = {}
    for code in sorted(tous, key=lambda c: (profondeur(c), c)):
        canon[code] = agrege_forme.get(code, [])
        par = parent(code)
        base = canon.get(par, []) if par else []
        propre = canon[code]
        # Le parent doit être un préfixe : sinon les deux chaînes ne
        # décrivent pas la même branche (variante d'époque), on ne nomme pas.
        if par and (len(propre) <= len(base)
                    or [_pli(x) for x in propre[:len(base)]] != [_pli(x) for x in base]):
            nom = None
        else:
            nom = _restitue(brutes.get(code, []), len(base), len(propre), propre[len(base):])
            if nom is None:
                nom = " ".join(propre[len(base):]).strip(" .-–—") or None
        if nom and CODE_INTERNE.search(nom):
            nom = None            # on a mordu sur le bloc suivant
        # Variantes : les chaînes minoritaires du code lui-même
        variantes: Counter = Counter()
        for f in chaines_forme.get(code, []):
            v = " ".join(f[len(base):]).strip(" .-–—")
            if v:
                variantes[v] += 1
        concepts[code] = {
            "code": code,
            "label": nom,
            "parent": par,
            "depth": profondeur(code),
            "freq": freq.get(code, 0),
            "variantes": dict(variantes.most_common(5)),
        }

    nommes = sum(1 for c in concepts.values() if c["label"])
    print(f"\ndécisions lues    : {n_dec}")
    print(f"blocs d'analyse   : {n_blocs}")
    print(f"concepts          : {len(concepts)}")
    print(f"  nommés          : {nommes} ({100.0*nommes/max(1,len(concepts)):.1f} %)")
    print(f"  sans nom        : {len(concepts)-nommes}")

    # ── Tests de recette, binaires ──────────────────────────────────────
    par_parent: dict[str, list[str]] = defaultdict(list)
    for c in concepts.values():
        if c["label"] and c["parent"]:
            par_parent[c["parent"]].append(c["label"])
    freres = sum(1 for labs in par_parent.values()
                 for lab, n in Counter(_pli(x) for x in labs).items() if n > 1)
    enfant_parent = sum(
        1 for c in concepts.values()
        if c["label"] and c["parent"] and concepts.get(c["parent"], {}).get("label")
        and _pli(c["label"]) == _pli(concepts[c["parent"]]["label"]))
    codes_dedans = sum(1 for c in concepts.values()
                       if c["label"] and CODE_INTERNE.search(c["label"]))
    print("\nTESTS DE RECETTE")
    for nom_test, valeur in (("frères homonymes", freres),
                             ("enfant = parent", enfant_parent),
                             ("code PCJA dans le libellé", codes_dedans)):
        print(f"  {'✓' if valeur == 0 else '✗'} {nom_test:28s} : {valeur}")

    print("\névidence de contrôle :")
    for c in ("37-04-04-02", "01-04", "01-04-04", "60-04-01-03-01",
              "19-01-01-03-02", "19-04-02-05-03"):
        e = concepts.get(c)
        print(f"  {c:18s} → {(e['label'] if e and e['label'] else '(sans nom)')[:78]}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(concepts, f, ensure_ascii=False, indent=1)
        print(f"\nécrit : {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
