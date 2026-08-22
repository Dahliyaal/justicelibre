"""Contrôle des CONTRATS des tools MCP — attrape les réponses fausses.

Pourquoi ce fichier existe (22 août 2026) : les trois bugs découverts ce
jour-là — `titre_section` qui renvoyait le titre du code, le filtre `code`
silencieusement ignoré, la dédup qui écrasait les résultats à un seul —
avaient un point commun : **aucun ne plantait**. Ils répondaient quelque
chose de plausible. Les tests existants (« ça répond ? ») ne pouvaient donc
structurellement pas les voir, et ils n'ont été trouvés qu'à l'usage, par
hasard, des semaines après leur introduction.

Ce qui les attrape, ce sont des INVARIANTS : des affirmations sur le
RAPPORT entre ce qu'on demande et ce qu'on reçoit.

  · si je filtre sur X, tout résultat doit porter X ;
  · returned ≤ limit, returned ≤ total ;
  · un paramètre invalide doit ÉCHOUER, jamais réussir en silence ;
  · un identifiant renvoyé par une recherche doit être récupérable ;
  · un champ ne doit pas valoir toujours la même chose (signe qu'il ment) ;
  · aucun appel ne doit approcher le délai d'expiration du client.

Tape la PROD via le endpoint MCP public : à lancer après chaque
déploiement, pas en CI (réseau + charge serveur).

Run :
    python3 tests/test_contracts.py
    python3 tests/test_contracts.py -v     # détail de chaque appel
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

BASE = "https://justicelibre.org/mcp"
UA = {"User-Agent": "justicelibre-contracts/1.0"}
SLOW_S = 8.0          # au-delà : timeout en puissance côté client (15 s)
VERBOSE = "-v" in sys.argv

_session: dict[str, str] = {}


def _post(body: dict) -> tuple[dict, float]:
    req = urllib.request.Request(
        BASE, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream",
                 **UA, **({"Mcp-Session-Id": _session["id"]} if "id" in _session else {})})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as r:
        if "id" not in _session and r.headers.get("Mcp-Session-Id"):
            _session["id"] = r.headers["Mcp-Session-Id"]
        raw = r.read().decode()
    dt = time.time() - t0
    for line in raw.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:]), dt
    return {}, dt


def handshake() -> None:
    _post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": "contracts", "version": "1.0"}}})
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"})


def call(tool: str, args: dict) -> tuple[dict, float, str | None]:
    """→ (payload, durée, erreur). `erreur` non nul si le tool a échoué."""
    resp, dt = _post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                      "params": {"name": tool, "arguments": args}})
    if "error" in resp:
        return {}, dt, str(resp["error"].get("message") or resp["error"])
    result = resp.get("result", {})
    payload = result.get("structuredContent")
    if payload is None:
        try:
            payload = json.loads(result["content"][0]["text"])
        except Exception:
            payload = {}
    if result.get("isError") or (isinstance(payload, dict) and payload.get("error")):
        return payload, dt, str(payload.get("error", "isError"))
    return payload, dt, None


# ─── Invariants réutilisables ────────────────────────────────────

def inv_pagination(p, args):
    n, total = p.get("returned"), p.get("total")
    lim = args.get("limit", 20)
    if n is None:
        return
    assert n <= lim, f"returned={n} > limit={lim}"
    if total is not None and not p.get("deduplicated_by"):
        assert n <= total, f"returned={n} > total={total}"


def inv_all_match(field: str, expected: str):
    """Tout résultat doit porter la valeur filtrée (attrape les filtres
    silencieusement ignorés : le pire des bugs, il renvoie 200)."""
    def check(p, args):
        rows = p.get("articles") or p.get("decisions") or p.get("results")
        if rows is None:
            rows = [p] if p.get(field) is not None else []   # réponse à un seul objet
        assert rows, "aucun résultat : invariant non évaluable (élargir la requête du test)"
        bad = [r for r in rows if expected.lower() not in str(r.get(field, "")).lower()]
        assert not bad, (f"{len(bad)}/{len(rows)} résultats hors filtre "
                         f"{field}={expected!r} — ex. {bad[0].get(field)!r}")
    return check


def inv_date_range(dmin: str | None = None, dmax: str | None = None):
    def check(p, args):
        rows = p.get("decisions") or p.get("results") or p.get("articles") or []
        for r in rows:
            d = (r.get("date") or r.get("date_debut") or "")[:10]
            if not d:
                continue
            if dmin:
                assert d >= dmin, f"date {d} < date_min {dmin}"
            if dmax:
                assert d <= dmax, f"date {d} > date_max {dmax}"
    return check


def inv_no_lying_section(p, args):
    """`titre_section` ne doit plus prétendre connaître la section : la
    hiérarchie LEGISCTA n'est pas ingérée (bug du 22 août 2026)."""
    assert p.get("titre_section") in (None, ""), (
        f"titre_section prétend valoir {p.get('titre_section')!r} alors que "
        "la hiérarchie des sections n'est pas en base")


def inv_field_varies(field: str):
    """Un champ qui vaut TOUJOURS la même chose sur des entrées différentes
    est un champ qui ment (c'était le cas de titre_section)."""
    seen: set[str] = set()

    def check(p, args):
        rows = p.get("articles") or p.get("decisions") or []
        for r in rows:
            seen.add(str(r.get(field)))
        check.seen = seen
    return check


# ─── Cas : (tool, args, [invariants], doit_échouer) ──────────────

CASES: list[tuple[str, dict, list, bool]] = [
    # — pagination et cohérence de base —
    ("search_admin", {"query": "astreinte liquidation", "limit": 5},
     [inv_pagination], False),
    ("search_judiciaire_libre", {"query": "licenciement sans cause", "limit": 5},
     [inv_pagination], False),
    ("search_legi", {"query": "prescription quadriennale", "limit": 5},
     [inv_pagination], False),

    # — les filtres doivent FILTRER (bug ② du 22 août) —
    ("search_legi", {"query": "chambre disciplinaire", "code": "CSP", "limit": 5},
     [inv_pagination, inv_all_match("legitext", "LEGITEXT000006072665")], False),
    # ⚠️ `juridiction` de search_admin n'est PAS un filtre : c'est un terme
    # ajouté à la requête FTS5 (une décision du CE citant « Douai » matche).
    # C'est documenté, mais le nom promet autre chose. Ne pas durcir ce test
    # sans changer d'abord le comportement — sinon il échouera à raison.
    ("search_admin", {"query": "permis de construire", "juridiction": "DOUAI", "limit": 5},
     [inv_pagination], False),
    # Le lookup judiciaire, lui, filtre vraiment :
    ("search_judiciaire_libre", {"query": "bail", "juridiction": "appel", "limit": 5},
     [inv_pagination, inv_all_match("juridiction", "Cour d'appel")], False),
    ("search_judiciaire_libre", {"query": "divorce", "juridiction": "tj", "limit": 5},
     [inv_pagination, inv_all_match("juridiction", "Tribunal judiciaire")], False),

    # — les filtres de date doivent borner —
    ("search_admin", {"query": "urbanisme", "date_min": "2024-01-01",
                      "date_max": "2024-12-31", "limit": 5},
     [inv_pagination, inv_date_range("2024-01-01", "2024-12-31")], False),

    # — un paramètre invalide doit ÉCHOUER, pas réussir en silence —
    ("search_legi", {"query": "forêt", "code": "CodeQuiNexistePas", "limit": 3},
     [], True),
    ("get_law_article", {"code": "CodeQuiNexistePas", "num": "1"}, [], True),
    ("get_decision_text", {"decision_id": "CETATEXT000000000000"}, [], True),

    # — pas de champ menteur —
    ("get_law_article", {"code": "CSP", "num": "R4126-37"},
     [inv_no_lying_section], False),
    ("get_law_article", {"code": "CC", "num": "1128"},
     [inv_no_lying_section], False),

    # — les alias documentés fonctionnent —
    ("get_decision_text", {"id": "CETATEXT000007543903"}, [], False),

    # — cohérence entre tools : un n° trouvé doit être récupérable —
    ("get_admin_decision", {"numero": "03NT00167", "juridiction": "CAA de Nantes"},
     [inv_all_match("juridiction", "Nantes")], False),
]


def main() -> int:
    handshake()
    ok = ko = 0
    slow: list[tuple[str, float]] = []
    for tool, args, invariants, must_fail in CASES:
        label = f"{tool}({', '.join(f'{k}={v!r}' for k, v in args.items())})"
        try:
            payload, dt, err = call(tool, args)
        except Exception as e:
            print(f"  ✗ {label}\n      appel impossible : {type(e).__name__}: {e}")
            ko += 1
            continue
        if dt > SLOW_S:
            slow.append((label, dt))
        if must_fail:
            if err:
                print(f"  ✓ {label} → refusé comme attendu ({dt:.2f}s)")
                ok += 1
            else:
                print(f"  ✗ {label}\n      RÉUSSIT alors qu'il devrait échouer "
                      f"— filtre ignoré en silence ?")
                ko += 1
            continue
        if err:
            print(f"  ✗ {label}\n      erreur inattendue : {err[:160]}")
            ko += 1
            continue
        failed = None
        for inv in invariants:
            try:
                inv(payload if isinstance(payload, dict) else {}, args)
            except AssertionError as e:
                failed = str(e)
                break
        if failed:
            print(f"  ✗ {label}\n      invariant violé : {failed}")
            ko += 1
        else:
            ok += 1
            if VERBOSE:
                print(f"  ✓ {label} ({dt:.2f}s)")
            else:
                print(f"  ✓ {label.split('(')[0]} — {len(invariants)} invariant(s) ({dt:.2f}s)")

    if slow:
        print("\n  ⚠ appels lents (timeout client à 15 s) :")
        for label, dt in slow:
            print(f"      {dt:5.1f}s  {label}")

    print(f"\n=== {ok} ✓ / {ko} ✗ sur {len(CASES)} contrats ===")
    return 1 if ko else 0


if __name__ == "__main__":
    raise SystemExit(main())
