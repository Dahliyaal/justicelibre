"""Banc de contrats du SITE : /api/search et /api/decision, tels que la page les appelle.

Pourquoi ce fichier existe (8 septembre 2026) : le MCP et le site partagent
les sources (sources/*.py) mais pas la couche qui les fédère — le site passe
par token_server.py → search_api.py, jamais testés en tant que tels. En
testant la page au navigateur, on a trouvé un filtre « Tribunaux
judiciaires » avalé à trois étages et servi comme appliqué. Ce banc
rejoue, en direct contre justicelibre.org, les invariants que la page
suppose vrais :

  - si je filtre sur X, tout résultat porte X ;
  - un paramètre invalide DOIT se voir (400 ou `filtres_ignores`), jamais
    être remplacé en silence par « pas de filtre » ;
  - une référence (pourvoi, RG, id, ECLI…) rend EXACTEMENT la décision ;
  - le tri trie, la pagination pagine, les bornes bornent.

Live (frappe la prod) : dans run_all.sh hors --offline.

Run :
    python3 tests/test_site_search.py
    JL_SITE=https://justicelibre.org python3 tests/test_site_search.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request

SITE = os.environ.get("JL_SITE", "https://justicelibre.org").rstrip("/")
LENT = 12.0   # au-delà, la page affiche « chargement » trop longtemps


def api(path: str, **params) -> tuple[int, dict, float]:
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{SITE}{path}?{qs}" if qs else f"{SITE}{path}"
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "justicelibre-tests/1.0"}), timeout=70) as r:
            code, body = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, body = e.code, e.read()
    dt = time.time() - t0
    try:
        data = json.loads(body or b"{}")
    except Exception:
        data = {"_raw": body[:200].decode("utf-8", "replace")}
    return code, data, dt


# ── invariants ───────────────────────────────────────────────────────────
def inv_ok(code, d):
    assert code == 200, f"HTTP {code} : {d}"


def inv_nonempty(code, d):
    inv_ok(code, d)
    assert d.get("results"), "aucun résultat : invariant non évaluable"


def inv_juri_any(*attendus):
    """Chaque résultat porte l'une des formes attendues dans `juridiction`."""
    def check(code, d):
        inv_nonempty(code, d)
        bad = [r for r in d["results"]
               if not any(a.lower() in (r.get("juridiction") or "").lower() for a in attendus)]
        assert not bad, (f"{len(bad)}/{len(d['results'])} hors filtre {attendus} — "
                         f"ex. {bad[0].get('juridiction')!r} ({bad[0].get('source')})")
    return check


def inv_sources_only(*srcs):
    def check(code, d):
        inv_nonempty(code, d)
        bad = {r.get("source") for r in d["results"]} - set(srcs)
        assert not bad, f"sources inattendues dans les résultats : {bad}"
        assert set(d.get("sources_queried", [])) <= set(srcs), (
            f"sources interrogées hors filtre : {d.get('sources_queried')}")
    return check


def inv_dates(dmin=None, dmax=None):
    def check(code, d):
        inv_nonempty(code, d)
        for r in d["results"]:
            dt = (r.get("date") or "")[:10]
            if not dt:
                continue
            if dmin:
                assert dt >= dmin, f"date {dt} < date_min {dmin} ({r.get('source')} {r.get('id')})"
            if dmax:
                assert dt <= dmax, f"date {dt} > date_max {dmax} ({r.get('source')} {r.get('id')})"
    return check


def inv_sorted(desc: bool):
    def check(code, d):
        inv_nonempty(code, d)
        dates = [(r.get("date") or "")[:10] for r in d["results"] if r.get("date")]
        exp = sorted(dates, reverse=desc)
        assert dates == exp, f"tri {'desc' if desc else 'asc'} non respecté : {dates[:8]}"
    return check


def inv_visible_rejet(param: str):
    """Un paramètre invalide doit se VOIR : 400, ou `filtres_ignores` le nommant."""
    def check(code, d):
        if code == 400:
            return
        assert code == 200, f"HTTP {code}"
        ign = d.get("filtres_ignores") or []
        assert any(f.get("parametre") == param for f in ign), (
            f"paramètre {param!r} invalide avalé en silence (ni 400 ni filtres_ignores)")
    return check


def inv_citation(numero: str | None = None, id_: str | None = None, date: str | None = None):
    def check(code, d):
        inv_nonempty(code, d)
        assert d.get("citation_match") is True or d.get("intent") in (
            "juritext", "cetatext", "ecli", "celex", "pourvoi", "rg", "dce_id", "itemid_hudoc"), (
            f"la référence n'a pas été reconnue comme telle (intent={d.get('intent')!r})")
        r = d["results"][0]
        if numero:
            n1 = (r.get("numero") or "").replace(".", "").replace(" ", "").replace("/", "")
            n2 = numero.replace(".", "").replace(" ", "").replace("/", "")
            assert n2 in n1 or n1 in n2, f"numéro servi {r.get('numero')!r} ≠ demandé {numero!r}"
        if id_:
            assert r.get("id") == id_, f"id servi {r.get('id')!r} ≠ {id_!r}"
        if date:
            assert (r.get("date") or "")[:10] == date, f"date servie {r.get('date')!r} ≠ {date}"
    return check


def inv_http(expected: int):
    def check(code, d):
        assert code == expected, f"HTTP {code} attendu {expected} : {str(d)[:120]}"
    return check


def inv_limit(n: int):
    def check(code, d):
        inv_ok(code, d)
        assert len(d.get("results", [])) <= n, f"{len(d['results'])} résultats > limit {n}"
    return check


def inv_expansion(flag: bool):
    def check(code, d):
        inv_ok(code, d)
        assert d.get("expansion_appliquee") is flag, f"expansion_appliquee={d.get('expansion_appliquee')}"
    return check


def inv_text():
    def check(code, d):
        inv_ok(code, d)
        txt = d.get("full_text") or d.get("texte") or d.get("text") or ""
        assert len(txt) > 200, f"texte absent ou trop court ({len(txt)} car.) : clés {sorted(d)[:12]}"
    return check


# ── cas ──────────────────────────────────────────────────────────────────
S = "/api/search"
CAS = [
    # — familles de juridiction : chaque option de la page —
    (S, dict(q="bail", juridiction="cass", sources="dila", limit=8), [inv_juri_any("Cour de cassation")]),
    (S, dict(q="bail", juridiction="ca", sources="dila", limit=8), [inv_juri_any("Cour d'appel")]),
    (S, dict(q="bail", juridiction="tj", sources="dila", limit=8),
     [inv_juri_any("Tribunal judiciaire", "Tribunal de grande instance", "Tribunal d'instance")]),
    (S, dict(q="liberté", juridiction="constit", sources="dila", limit=8), [inv_juri_any("Conseil constitutionnel")]),
    (S, dict(q="bail", juridiction="judic", limit=8), [inv_sources_only("dila")]),
    (S, dict(q="urbanisme", juridiction="admin", limit=8), [inv_sources_only("ariane", "admin")]),
    (S, dict(q="urbanisme", juridiction="ce", limit=8),
     [inv_sources_only("ariane", "admin"), inv_juri_any("Conseil d'État", "Conseil d'Etat")]),
    (S, dict(q="urbanisme", juridiction="caa", lieu="CAA59", limit=8),
     [inv_sources_only("admin"), inv_juri_any("Douai")]),
    (S, dict(q="urbanisme", juridiction="ta", lieu="TA59", limit=8),
     [inv_sources_only("admin"), inv_juri_any("Lille")]),
    (S, dict(q="expulsion", juridiction="europ", limit=8), [inv_sources_only("cedh", "cjue")]),
    (S, dict(q="expulsion", juridiction="cedh", limit=8), [inv_sources_only("cedh")]),
    (S, dict(q="données personnelles", juridiction="cjue", limit=8), [inv_sources_only("cjue")]),
    # — un filtre inconnu ne doit pas devenir « pas de filtre » en silence —
    (S, dict(q="bail", juridiction="tribunal_de_mars", sources="dila", limit=3), [inv_visible_rejet("juridiction")]),
    (S, dict(q="bail", sources="mars", limit=3), [inv_visible_rejet("sources")]),
    # — dates —
    (S, dict(q="bail", sources="dila", date_min="2026-01-01", limit=10), [inv_dates(dmin="2026-01-01")]),
    (S, dict(q="bail", sources="dila", date_max="2010-12-31", limit=10), [inv_dates(dmax="2010-12-31")]),
    (S, dict(q="urbanisme", date_min="2024-01-01", date_max="2024-12-31", limit=10),
     [inv_dates("2024-01-01", "2024-12-31")]),
    (S, dict(q="bail", sources="dila", date_min="01/01/2026", limit=3), [inv_visible_rejet("date_min")]),
    (S, dict(q="bail", sources="dila", date_min="2026-13-45", limit=3), [inv_visible_rejet("date_min")]),
    # — tri —
    (S, dict(q="bail", sources="dila", sort="date_desc", limit=10), [inv_sorted(desc=True)]),
    (S, dict(q="bail", sources="dila", sort="date_asc", limit=10), [inv_sorted(desc=False)]),
    (S, dict(q="bail", sources="dila", sort="n_importe_quoi", limit=3), [inv_visible_rejet("sort")]),
    # — bornes —
    (S, dict(q="bail", sources="dila", limit=500), [inv_limit(100)]),
    (S, dict(q="ab"), [inv_http(400)]),
    (S, dict(q=""), [inv_http(400)]),
    (S, dict(q="x" * 600), [inv_http(400)]),
    # — thésaurus —
    (S, dict(q="harcèlement moral", sources="dila", expand=1, limit=5), [inv_expansion(True), inv_nonempty]),
    (S, dict(q="harcèlement moral", sources="dila", expand=0, limit=5), [inv_expansion(False), inv_nonempty]),
    # — syntaxes que la page annonce comme acceptées —
    (S, dict(q="liberté AND signalement", sources="dila", limit=5), [inv_nonempty]),
    (S, dict(q="liberté & signalement", sources="dila", limit=5), [inv_nonempty]),
    (S, dict(q='"vie privée" SAUF médical', sources="dila", limit=5), [inv_nonempty]),
    (S, dict(q="signal*", sources="dila", limit=5), [inv_nonempty]),
    (S, dict(q="garde-à-vue", sources="dila", limit=5), [inv_nonempty]),
    (S, dict(q="tribunal d'instance bail", sources="dila", limit=5), [inv_nonempty]),
    # — syntaxes cassées : jamais de 500 —
    (S, dict(q='"phrase jamais fermée', sources="dila", limit=3), [inv_ok]),
    (S, dict(q="(bail OR", sources="dila", limit=3), [inv_ok]),
    (S, dict(q="AND bail", sources="dila", limit=3), [inv_ok]),
    (S, dict(q="bail'; DROP TABLE decisions; --", sources="dila", limit=3), [inv_ok]),
    (S, dict(q="🙂 bail", sources="dila", limit=3), [inv_ok]),
    # — références : servir EXACTEMENT la décision —
    (S, dict(q="24-11.587", limit=5), [inv_citation(numero="24-11.587", date="2025-11-19")]),
    (S, dict(q="RG 26/03307 tj meaux", limit=5), [inv_citation(numero="26/03307")]),
    (S, dict(q="CETATEXT000007641393", limit=5), [inv_citation(id_="CETATEXT000007641393")]),
    (S, dict(q="JURITEXT000007031693", limit=5), [inv_citation(id_="JURITEXT000007031693")]),
    (S, dict(q="ECLI:FR:CCASS:2025:SO01066", limit=5), [inv_citation(numero="24-11.587")]),
    (S, dict(q="tribunal des conflits 8 février 1873", limit=5), [inv_citation(date="1873-02-08")]),
    (S, dict(q="62019CJ0030", limit=5), [inv_citation()]),
    (S, dict(q="conseil d'état 3 février 1989 74052", limit=5), [inv_citation(numero="74052", date="1989-02-03")]),
    # — pagination : page 2 ≠ page 1 —
    ("_pagination", dict(q="bail", sources="dila", limit=10), []),
    # — texte intégral —
    ("/api/decision", dict(source="dila", id="JURITEXT000007031693"), [inv_text()]),
    ("/api/decision", dict(source="dila", id="6079723d9ba5988459c49da5"), [inv_text()]),
    ("/api/decision", dict(source="dila", id="JURITEXT999999999999"), [inv_http(404)]),
    ("/api/decision", dict(source="mars", id="x"), [inv_http(404)]),
    ("/api/decision", dict(source="admin", id="CETATEXT000007641393"), [inv_text()]),
    ("/api/decision", dict(source="dila"), [inv_http(400)]),
]


def run_pagination(params):
    c1, d1, t1 = api(S, **params, offset=0)
    c2, d2, t2 = api(S, **params, offset=10)
    inv_nonempty(c1, d1); inv_nonempty(c2, d2)
    i1 = {r["id"] for r in d1["results"]}
    i2 = {r["id"] for r in d2["results"]}
    assert i1.isdisjoint(i2), f"page 2 répète la page 1 : {len(i1 & i2)} ids communs"
    return max(t1, t2)


def main() -> int:
    ok = ko = 0
    lents = []
    for path, params, invs in CAS:
        label = f"{path} {params}"
        try:
            if path == "_pagination":
                dt = run_pagination(params)
            else:
                code, data, dt = api(path, **params)
                for inv in invs:
                    inv(code, data)
            ok += 1
            print(f"  ✓ {label[:110]}  ({dt:.1f}s)")
            if dt > LENT:
                lents.append((dt, label))
        except AssertionError as e:
            ko += 1
            print(f"  ✗ {label[:110]}\n      → {e}")
        except Exception as e:
            ko += 1
            print(f"  ✗ {label[:110]}\n      → {type(e).__name__}: {e}")
    if lents:
        print(f"\n  ⚠ appels lents (> {LENT:.0f} s, la page affiche « chargement ») :")
        for dt, label in sorted(lents, reverse=True):
            print(f"      {dt:5.1f}s  {label[:100]}")
    print(f"\n=== {ok} ✓ / {ko} ✗ sur {ok + ko} contrats du site ===")
    return 0 if ko == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
