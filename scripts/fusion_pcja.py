"""Fusionne les deux reconstructions du PCJA : v4 en autorité, v2 en appoint.

POURQUOI UNE FUSION (30 août 2026)
──────────────────────────────────
Aucune des deux reconstructions n'est bonne seule, et un arbitrage à
l'aveugle l'a mesuré :

  v2 (en production)  6 293 noms (97,8 %) mais **21,1 % d'erreur**, et
                      216 fratries homonymes — un état impossible dans une
                      nomenclature, signature de son décalage de niveaux.
  v4 (flux « point ») 3 624 noms (56,0 %) mais 6 fratries, 0 enfant
                      portant le nom de son parent, chaque nom validé par
                      comptage de segments et attesté ≥ 2 fois.

La v4 est fiable là où elle parle ; la v2 couvre davantage mais se trompe
une fois sur cinq, de façon PLAUSIBLE — donc indétectable à l'usage.

RÈGLE DE FUSION
───────────────
1. Le nom de la v4 l'emporte toujours : il est auto-validé et attesté.
2. Là où la v4 se tait, on reprend celui de la v2 — mais SEULEMENT s'il
   passe les contrôles structurels ci-dessous. Un nom repris est marqué
   `origine: "v2"` pour rester traçable.
3. Sinon `label: null`. Un trou déclaré vaut mieux qu'un nom faux.

CONTRÔLES APPLIQUÉS AUX NOMS REPRIS DE LA V2
────────────────────────────────────────────
- pas le nom d'un ancêtre (signature du décalage de niveau) ;
- pas identique à celui d'un frère déjà nommé (impossible dans une
  nomenclature : deux frères homonymes sont indiscernables) ;
- pas de code PCJA à l'intérieur du libellé (on a mordu sur le bloc
  suivant) ;
- pas de marqueur de titre d'analyse (« 1) », « RJ1 », tirets
  demi-cadratins, guillemets) ;
- pas plus de 250 caractères.

Usage :
    python3 scripts/fusion_pcja.py --v4 pcja_v4.json --v2 pcja_v2.json --json sortie.json
"""
import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict

MARQUEURS_TITRE = re.compile(r"\b[1-9]\)\s|\[RJ|,RJ|\bRJ[123]\b|–|—|«|»|\s{4,}")
CODE_INTERNE = re.compile(r"\b\d{2,3}(?:-\d{1,3}){2,}\b")
LONGUEUR_MAX = 250


def _pli(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).upper().strip(" .,;:-–—")


def ancetres(code: str) -> list[str]:
    p = code.split("-")
    return ["-".join(p[: i + 1]) for i in range(len(p) - 1)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--v4", required=True)
    ap.add_argument("--v2", required=True)
    ap.add_argument("--json")
    args = ap.parse_args()

    v4 = json.load(open(args.v4, encoding="utf-8"))
    v2 = json.load(open(args.v2, encoding="utf-8"))

    fusion: dict[str, dict] = {}
    for code in sorted(set(v4) | set(v2), key=lambda c: (len(c.split("-")), c)):
        a = v4.get(code) or {}
        b = v2.get(code) or {}
        base = dict(a) if a else dict(b)
        base["code"] = code
        base["parent"] = "-".join(code.split("-")[:-1]) or None
        base["depth"] = len(code.split("-"))
        base["label"] = a.get("label")
        base["origine"] = "v4" if a.get("label") else None
        base["attestations"] = a.get("attestations", 0)
        base.setdefault("freq", b.get("freq", 0))
        fusion[code] = base

    # Reprise de la v2, contrôlée, par profondeur croissante : les contrôles
    # ont besoin des noms des ancêtres et des frères déjà arbitrés.
    freres: dict[str, set[str]] = defaultdict(set)
    for c in fusion.values():
        if c["label"] and c["parent"]:
            freres[c["parent"]].add(_pli(c["label"]))

    repris = rejetes = Counter(), Counter()
    n_repris = 0
    motifs: Counter = Counter()
    for code in sorted(fusion, key=lambda c: len(c.split("-"))):
        e = fusion[code]
        if e["label"]:
            continue
        cand = (v2.get(code) or {}).get("label")
        if not cand:
            continue
        p = _pli(cand)
        if len(cand) > LONGUEUR_MAX:
            motifs["trop long"] += 1
            continue
        if CODE_INTERNE.search(cand):
            motifs["code PCJA dedans"] += 1
            continue
        if MARQUEURS_TITRE.search(cand):
            motifs["marqueur de titre"] += 1
            continue
        if any(_pli((fusion.get(a) or {}).get("label")) == p for a in ancetres(code)):
            motifs["nom d'un ancêtre"] += 1
            continue
        if e["parent"] and p in freres[e["parent"]]:
            motifs["homonyme d'un frère"] += 1
            continue
        e["label"] = cand
        e["origine"] = "v2"
        n_repris += 1
        if e["parent"]:
            freres[e["parent"]].add(p)

    nommes = sum(1 for c in fusion.values() if c["label"])
    par_v4 = sum(1 for c in fusion.values() if c.get("origine") == "v4")
    print(f"concepts          : {len(fusion)}")
    print(f"  nommés          : {nommes} ({100.0*nommes/len(fusion):.1f} %)")
    print(f"    par la v4     : {par_v4}")
    print(f"    repris de v2  : {n_repris}")
    print(f"  sans nom        : {len(fusion)-nommes}")
    print("\nnoms de la v2 ÉCARTÉS par les contrôles :")
    for motif, n in motifs.most_common():
        print(f"  {motif:22s} : {n}")

    # ── Tests de recette sur le résultat fusionné ───────────────────────
    par_parent = defaultdict(list)
    for c in fusion.values():
        if c["label"] and c["parent"]:
            par_parent[c["parent"]].append(c["label"])
    f_hom = sum(1 for labs in par_parent.values()
                for _, n in Counter(_pli(x) for x in labs).items() if n > 1)
    e_par = sum(1 for c in fusion.values()
                if c["label"] and c["parent"]
                and (fusion.get(c["parent"]) or {}).get("label")
                and _pli(c["label"]) == _pli(fusion[c["parent"]]["label"]))
    c_ded = sum(1 for c in fusion.values() if c["label"] and CODE_INTERNE.search(c["label"]))
    print("\nTESTS DE RECETTE       (v2 seule : 216 / 14 / 3)")
    for nom, v in (("fratries homonymes", f_hom), ("enfant = parent", e_par),
                   ("code PCJA dans le libellé", c_ded)):
        print(f"  {'✓' if v == 0 else '✗'} {nom:28s} : {v}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(fusion, f, ensure_ascii=False, indent=1)
        print(f"\nécrit : {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
