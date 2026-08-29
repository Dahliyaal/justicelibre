"""Numéros de pourvoi réutilisés : un lookup ne doit jamais taire un homonyme.

Pourquoi ce fichier existe (29 août 2026) : le Conseil d'État a réattribué
ses numéros de pourvoi d'une époque à l'autre. Le lookup par numéro
récupérait jusqu'à 5 lignes du warehouse, renvoyait `results[0]` — l'ordre
des rowid, donc la plus ancienne — et jetait les autres sans un mot.

Le cas qui l'a révélé : `get_ce_decision("74052")` servait l'arrêt du
29 octobre 1969 sur les quotas d'écrasement d'un moulin, alors que le MÊME
numéro porte aussi CE, Ass., 3 février 1989, « Compagnie Alitalia »
(CETATEXT000007754163), qui est bel et bien dans la base. Un agent en a
conclu qu'Alitalia était introuvable et l'a classée « invérifiable ».

Mesure du 29 août 2026 sur le bulk JADE : 7 938 numéros du CE portés par
plusieurs décisions, soit 16 143 décisions exposées à cette confusion.

Le correctif ne CHOISIT pas à la place de l'appelant — la décision servie
reste la même qu'avant — mais joint `homonymes` et `avertissement`.

Run :
    python3 tests/test_homonymes_numero.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from sources.jade_remote import _signaler_homonymes  # noqa: E402

MOULIN_1969 = {
    "id": "CETATEXT000007641393",
    "juridiction": "Conseil d'Etat",
    "formation": "3 / 6 SSR",
    "date": "1969-10-29",
    "numero": "74052",
    "titre": "Conseil d'Etat, 3 / 6 SSR, du 29 octobre 1969, 74052",
}
ALITALIA_1989 = {
    "id": "CETATEXT000007754163",
    "juridiction": "Conseil d'Etat",
    "formation": "Assemblée",
    "date": "1989-02-03",
    "numero": "74052",
    "titre": "Conseil d'Etat, Assemblée, du 3 février 1989, 74052",
}


def test_homonyme_signale():
    """Le cas Alitalia : la seconde décision ne doit plus disparaître."""
    got = _signaler_homonymes(MOULIN_1969, [MOULIN_1969, ALITALIA_1989])
    assert "homonymes" in got, "l'homonyme a été tu — c'est le bug d'origine"
    assert len(got["homonymes"]) == 1
    assert got["homonymes"][0]["id"] == ALITALIA_1989["id"]
    assert got["homonymes"][0]["date"] == "1989-02-03"
    assert got["homonymes"][0]["formation"] == "Assemblée", (
        "la formation doit figurer : c'est elle qui désambiguïse une citation"
    )
    assert "74052" in got["avertissement"]
    assert "1969-10-29" in got["avertissement"], (
        "l'avertissement doit dire QUELLE décision est servie"
    )


def test_decision_servie_inchangee():
    """Aucun changement de comportement : c'est toujours la même qui sort."""
    got = _signaler_homonymes(MOULIN_1969, [MOULIN_1969, ALITALIA_1989])
    for champ, valeur in MOULIN_1969.items():
        assert got[champ] == valeur, f"{champ} a bougé — régression"


def test_cas_unique_intact():
    """Sans homonyme, la réponse ne doit pas être polluée."""
    got = _signaler_homonymes(MOULIN_1969, [MOULIN_1969])
    assert "homonymes" not in got
    assert "avertissement" not in got
    assert got is MOULIN_1969, "pas de copie inutile quand il n'y a rien à dire"


def test_pas_de_mutation_de_lentree():
    """L'annotation ne doit pas contaminer le dict d'origine (cache, réutilisation)."""
    source = dict(MOULIN_1969)
    _signaler_homonymes(source, [source, ALITALIA_1989])
    assert "homonymes" not in source
    assert "avertissement" not in source


def test_le_principal_ne_sautoclasse_pas_homonyme():
    """La décision servie ne doit pas se retrouver dans sa propre liste."""
    got = _signaler_homonymes(ALITALIA_1989, [MOULIN_1969, ALITALIA_1989])
    ids = [h["id"] for h in got["homonymes"]]
    assert ALITALIA_1989["id"] not in ids
    assert ids == [MOULIN_1969["id"]]


def test_champs_vides_omis():
    """Une formation absente ne doit pas produire une clé vide trompeuse."""
    sans_formation = dict(ALITALIA_1989, formation="")
    got = _signaler_homonymes(MOULIN_1969, [MOULIN_1969, sans_formation])
    assert "formation" not in got["homonymes"][0]


if __name__ == "__main__":
    fails = 0
    for nom, fn in sorted(globals().items()):
        if nom.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {nom}")
            except AssertionError as e:
                fails += 1
                print(f"  FAIL {nom}: {e}")
    print(f"\n{'✗ ' + str(fails) + ' échec(s)' if fails else '✓ tous les cas passent'}")
    sys.exit(1 if fails else 0)
