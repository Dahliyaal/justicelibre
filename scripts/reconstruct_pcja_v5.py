"""Reconstruction du PCJA — v5 : amorçage par les points, puis désambiguïsation
des chaînes à tirets par gabarit d'ancêtres.

L'HISTOIRE COURTE (30 août 2026)
────────────────────────────────
La difficulté tient en une ligne : dans la convention ancienne, le tiret
sépare les rubriques ET figure DANS certains noms.

    55    = « Professions - charges et offices »          UN nom
    01-02 = « Validité des actes administratifs - Compétence »
    18-04 = « Dettes des collectivités publiques - Prescription quadriennale »
    66-07-02 = « Autorisation administrative - Salariés non protégés -
                 Licenciement pour motif économique »     DEUX tirets internes

Quatre tentatives, toutes mesurées par audit à l'aveugle :
  v1  découpe naïve            → 3 526 étiquettes « <inconnu> » sur 4 582
  v2  découpe + filtres        → 14,7 % de libellés faux, 216 fratries
                                 homonymes (signature du décalage de niveau)
  v3  soustraction du parent   → 58 % d'erreur, PIRE : ne sait pas où finit
                                 le niveau demandé
  v4  flux « point » seul      →  2,0 % de faux, mais 3 624 codes seulement

LA V5 GARDE LA RIGUEUR DE LA V4 ET RÉCUPÈRE LA COUVERTURE
──────────────────────────────────────────────────────────
1. AMORÇAGE. Les conventions à points (« A. B. C. ») et point-tiret
   (« A. - B. - C. ») sont NON AMBIGUËS. On ne retient une ligne que si son
   nombre de segments égale la profondeur du code — auto-validation, aucun
   réglage. Cela nomme d'emblée quelques milliers de codes.

2. DÉSAMBIGUÏSATION. Pour une chaîne à tirets, on essaie toutes les façons
   de regrouper les segments-tirets en autant de niveaux que le code a de
   profondeur. On ne retient une découpe que si :
     - chaque niveau déjà connu par l'amorçage correspond exactement, et
     - il n'existe QU'UNE SEULE découpe compatible.
   Sur « PROFESSIONS - CHARGES ET OFFICES - CONDITIONS D'EXERCICE - MEDECINS »
   pour un code de profondeur 3, savoir que le niveau 1 vaut « Professions -
   charges et offices » impose le reste : « Conditions d'exercice » puis
   « Médecins ». Une seule lecture tient debout.

3. ITÉRATION. Chaque nom nouvellement établi devient un gabarit pour le tour
   suivant. On recommence jusqu'à ce que plus rien ne bouge.

Ce qu'on ne sait pas faire reste `label: null`. Un silence se répare ; un
nom faux mais plausible envoie l'utilisateur sur le mauvais niveau du plan
sans qu'il puisse s'en apercevoir.

Usage :
    python3 scripts/reconstruct_pcja_v5.py --json sortie.json
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
MIN_ATTESTATIONS = 2
MAX_TOURS = 6

MARQUEUR_BLOC = re.compile(r"\[[0-9A-Z]{1,6}(?:\s+[A-Z]+)?\]")
CODE_EN_TETE = re.compile(r"^\s*(\d{1,3}(?:-\d{1,3}){0,7})(?:,RJ\d+)?\s+(.*)$", re.S)
SEP_POINT = re.compile(r"\.\s*-\s*(?=[A-Za-zÀ-ÿ])|\.\s+(?=[A-Za-zÀ-ÿ])")
SEP_TIRET = re.compile(r"\s+-\s+")
# Le titre d'analyse s'ouvre sur un tiret COLLÉ au mot suivant.
DEBUT_TITRE_COLLE = re.compile(r"\s-(?=\S)")


def profondeur(code: str) -> int:
    return len(code.split("-"))


def ancetres(code: str) -> list[str]:
    p = code.split("-")
    return ["-".join(p[: i + 1]) for i in range(len(p))]


def _pli(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
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


def sans_titre(reste: str) -> str:
    m = DEBUT_TITRE_COLLE.search(reste)
    return (reste[: m.start()] if m else reste).strip()


def decoupe_points(hier: str) -> list[str] | None:
    if not SEP_POINT.search(hier):
        return None
    parts = [p.strip(" .;") for p in SEP_POINT.split(hier)]
    parts = [p for p in parts if len(p) >= 2]
    return parts or None


# Signatures d'un titre d'analyse. Dans la convention à tirets, le titre
# n'est pas toujours introduit par un tiret collé : il commence parfois par
# « - 1) … » ou « - EXISTENCE [RJ1] ». Sans cette coupe, ses morceaux
# entraient dans le regroupement et un code recevait « ACTE ANORMAL DE
# GESTION. - 1) QUALIFICATION SUSCEPTIBLE DE… » (mesuré le 30 août 2026).
MARQUEUR_TITRE = re.compile(r"^\s*[1-9]\)|\[RJ|,RJ|\bRJ[123]\b|–|—|«|»")


def decoupe_tirets(hier: str) -> list[str] | None:
    parts = [p.strip(" .;") for p in SEP_TIRET.split(hier)]
    gardes = []
    for p in parts:
        if MARQUEUR_TITRE.search(p):
            break          # tout ce qui suit appartient au titre
        if len(p) >= 2:
            gardes.append(p)
    return gardes or None


def regroupements(morceaux: list[str], niveaux: int):
    """Toutes les façons de regrouper `morceaux` consécutifs en `niveaux` blocs.

    C'est le cœur de la désambiguïsation : « A - B - C - D » pour un code de
    profondeur 3 peut se lire « A‑B | C | D », « A | B‑C | D » ou
    « A | B | C‑D ». Les noms d'ancêtres déjà connus éliminent les mauvaises.
    """
    n = len(morceaux)
    if niveaux > n:
        return
    def rec(debut: int, restants: int, acc: list[str]):
        if restants == 1:
            yield acc + [" - ".join(morceaux[debut:])]
            return
        for fin in range(debut + 1, n - restants + 2):
            yield from rec(fin, restants - 1, acc + [" - ".join(morceaux[debut:fin])])
    yield from rec(0, niveaux, [])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=JADE_DEFAUT)
    ap.add_argument("--json")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    sql = ("SELECT sommaire, abstrats FROM jade_decisions "
           "WHERE (sommaire IS NOT NULL AND length(sommaire) > 30) "
           "   OR (abstrats IS NOT NULL AND length(abstrats) > 30)")
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"

    lignes_points: list[tuple[str, list[str]]] = []
    lignes_tirets: list[tuple[str, list[str]]] = []
    freq: Counter = Counter()
    n_dec = 0
    print("[pcja-v5] lecture…", flush=True)
    for sommaire, abstrats in conn.execute(sql):
        n_dec += 1
        for texte in (abstrats, sommaire):
            for code, reste in blocs(texte or ""):
                freq[code] += 1
                hier = sans_titre(reste)
                if not hier:
                    continue
                pts = decoupe_points(hier)
                if pts and len(pts) == profondeur(code):
                    lignes_points.append((code, pts))
                    continue
                tir = decoupe_tirets(hier)
                if tir and len(tir) >= profondeur(code):
                    lignes_tirets.append((code, tir))
        if n_dec % 50000 == 0:
            print(f"  {n_dec} décisions | points {len(lignes_points)} | "
                  f"tirets {len(lignes_tirets)}", flush=True)
    conn.close()

    # ── 1. Amorçage : le flux à points, auto-validé ─────────────────────
    votes: dict[str, Counter] = defaultdict(Counter)
    for code, parts in lignes_points:
        for a, nom in zip(ancetres(code), parts):
            votes[a][nom] += 1

    def arrete() -> dict[str, str]:
        out = {}
        for code, cnt in votes.items():
            nom, n = cnt.most_common(1)[0]
            if n >= MIN_ATTESTATIONS:
                out[code] = nom
        return out

    connus = arrete()
    print(f"\n[amorçage] {len(lignes_points)} lignes à points → {len(connus)} codes nommés")

    # ── 2. Désambiguïsation itérative des chaînes à tirets ──────────────
    for tour in range(1, MAX_TOURS + 1):
        avant = len(connus)
        plis = {c: _pli(v) for c, v in connus.items()}
        nouveaux = 0
        for code, morceaux in lignes_tirets:
            anc = ancetres(code)
            compatibles = []
            for decoupe in regroupements(morceaux, len(anc)):
                if all(a not in plis or plis[a] == _pli(d)
                       for a, d in zip(anc, decoupe)):
                    compatibles.append(decoupe)
                    if len(compatibles) > 1:
                        break          # ambigu → on n'apprend rien
            if len(compatibles) == 1:
                for a, nom in zip(anc, compatibles[0]):
                    votes[a][nom] += 1
                    nouveaux += 1
        connus = arrete()
        print(f"[tour {tour}] +{len(connus)-avant} codes (votes ajoutés : {nouveaux})")
        if len(connus) == avant:
            break

    # ── 3. Sortie ───────────────────────────────────────────────────────
    tous: set[str] = set()
    for c in freq:
        tous.update(ancetres(c))
    tous.update(votes)

    concepts = {}
    for code in sorted(tous, key=lambda c: (profondeur(c), c)):
        cnt = votes.get(code)
        label = connus.get(code)
        parts = code.split("-")
        concepts[code] = {
            "code": code,
            "label": label,
            "parent": "-".join(parts[:-1]) if len(parts) > 1 else None,
            "depth": len(parts),
            "freq": freq.get(code, 0),
            "attestations": cnt[label] if (cnt and label) else 0,
            "variantes": dict(cnt.most_common(5)) if cnt else {},
        }

    nommes = sum(1 for c in concepts.values() if c["label"])
    print(f"\nconcepts          : {len(concepts)}")
    print(f"  nommés          : {nommes} ({100.0*nommes/len(concepts):.1f} %)")
    print(f"  sans nom        : {len(concepts)-nommes}")

    par_parent = defaultdict(list)
    for c in concepts.values():
        if c["label"] and c["parent"]:
            par_parent[c["parent"]].append(c["label"])
    f_hom = sum(1 for labs in par_parent.values()
                for _, n in Counter(_pli(x) for x in labs).items() if n > 1)
    e_par = sum(1 for c in concepts.values()
                if c["label"] and c["parent"]
                and (concepts.get(c["parent"]) or {}).get("label")
                and _pli(c["label"]) == _pli(concepts[c["parent"]]["label"]))
    c_ded = sum(1 for c in concepts.values()
                if c["label"] and re.search(r"\b\d{2,3}(?:-\d{1,3}){2,}\b", c["label"]))
    print("\nTESTS DE RECETTE     (v2 en production : 216 / 14 / 3)")
    for nom, v in (("fratries homonymes", f_hom), ("enfant = parent", e_par),
                   ("code PCJA dans le libellé", c_ded)):
        print(f"  {'✓' if v == 0 else '✗'} {nom:28s} : {v}")

    print("\névidence de contrôle :")
    for c in ("55", "55-02", "55-03-01", "01-02", "01-04", "01-01-05", "18-04",
              "36-05-04-01", "60-04-01-03-01", "19-04-02-01-04-082", "37-04-04-02"):
        e = concepts.get(c)
        lab = e["label"] if e and e["label"] else "(sans nom)"
        att = f"  [{e['attestations']}×]" if e and e["attestations"] else ""
        print(f"  {c:22s} → {lab[:60]}{att}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(concepts, f, ensure_ascii=False, indent=1)
        print(f"\nécrit : {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
