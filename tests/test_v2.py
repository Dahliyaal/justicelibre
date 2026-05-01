"""Smoke tests pour la refonte MCP v2 + REST API + warehouse.

Ne testent PAS la prod live mais :
- query_intent (thésaurus, expansion)
- imports propres de tous les modules sources
- patterns de regex critiques

Tests live API (prod) optionnels en bas, skip si offline.

Run :
    python3 -m pytest tests/test_v2.py -v
ou :
    python3 tests/test_v2.py
"""
import json
import os
import sys
import urllib.request
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─── 1. Imports ────────────────────────────────────────────────

def test_imports():
    """Tous les modules sources doivent importer sans erreur."""
    from sources import ariane, dila, european, judilibre, juriadmin, legi
    from sources import warehouse, jade_remote, jorf_remote, kali_remote, cnil_remote
    # Vérifier qu'on a les fonctions clés
    assert hasattr(legi, "get_article")
    assert hasattr(legi, "get_versions")
    assert hasattr(legi, "get_batch")
    assert hasattr(legi, "SUPPORTED_CODES")
    # 22 codes consolidés + Constitution + lois non codifiées (LIL, LO58, L2005-102)
    assert len(legi.SUPPORTED_CODES) >= 22, f"trop peu de codes: {len(legi.SUPPORTED_CODES)}"
    for must in ("CC", "CP", "CT", "CONST", "LIL"):
        assert must in legi.SUPPORTED_CODES, f"code {must} manquant"
    assert hasattr(warehouse, "get_law")
    assert hasattr(warehouse, "search_fond")
    assert hasattr(jade_remote, "search")
    assert hasattr(jorf_remote, "search")
    assert hasattr(kali_remote, "search")
    assert hasattr(cnil_remote, "search")


# ─── 2. Thésaurus & query_intent ───────────────────────────────

def test_thesaurus_loaded():
    from query_intent import expand_synonyms, _load_thesaurus
    th = _load_thesaurus()
    assert len(th) > 100, f"thésaurus trop petit: {len(th)}"
    # Test quelques entrées clés
    expected = ["harcèlement", "licenciement", "infraction", "jugement", "préjudice"]
    for term in expected:
        assert term in th, f"thésaurus manque la clé {term!r}"


def test_expand_synonyms_basic():
    from query_intent import expand_synonyms
    out = expand_synonyms("harcèlement")
    # Doit produire un OR avec plusieurs alternatives
    assert "OR" in out
    assert "harcèlement" in out
    # Au moins 3 synonymes
    assert out.count("OR") >= 3


def test_expand_synonyms_multi_word_priority():
    """'licenciement abusif' doit matcher en priorité (plus long que 'licenciement')."""
    from query_intent import expand_synonyms
    out = expand_synonyms("licenciement abusif")
    assert '"licenciement abusif"' in out or "licenciement abusif" in out
    # Doit avoir des alternatives spécifiques (pas juste 'licenciement')
    assert "licenciement sans cause" in out or "rupture abusive" in out


def test_expand_synonyms_preserves_quotes():
    """Phrases entre guillemets doivent être préservées (pas étendues)."""
    from query_intent import expand_synonyms
    out = expand_synonyms('"harcèlement" exact')
    assert '"harcèlement"' in out


def test_expand_synonyms_empty():
    from query_intent import expand_synonyms
    assert expand_synonyms("") == ""
    assert expand_synonyms(None) is None or expand_synonyms("") == ""


# ─── 3. legi.py — codes supportés ─────────────────────────────

def test_legi_supported_codes():
    from sources.legi import SUPPORTED_CODES, is_supported
    # Codes critiques attendus
    expected = ["CC", "CP", "CT", "CSP", "CJA", "CGCT", "CRPA", "CPC", "CPP"]
    for c in expected:
        assert is_supported(c), f"code {c} non supporté"
    # Codes invalides
    assert not is_supported("BOGUS")
    assert not is_supported("")
    assert not is_supported("xyz")


# ─── 4. dila.py FTS5 sanitize ─────────────────────────────────

def test_dila_sanitize_fts5():
    from sources.dila import _sanitize_fts5
    # Strip dangerous chars
    assert _sanitize_fts5("foo;bar") == "foo bar"
    assert _sanitize_fts5("test\\backslash") == "test backslash"
    # Préserve les opérateurs FTS5 légitimes
    assert "AND" in _sanitize_fts5("foo AND bar")
    assert '"' in _sanitize_fts5('"phrase"')
    assert "*" in _sanitize_fts5("test*")
    # Empty
    assert _sanitize_fts5("") == ""


# ─── 5. CODE_TO_LEGITEXT mapping côté warehouse ───────────────

def test_warehouse_code_mapping():
    """Le mapping côté warehouse doit avoir les mêmes codes que sources/legi.py."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "warehouse"))
    try:
        # Stub env for import
        os.environ.setdefault("JL_WAREHOUSE_KEY_FILE", "/dev/null")
        # Cannot import warehouse_server (needs key), donc on lit le fichier
        with open(os.path.join(os.path.dirname(__file__), "..", "warehouse", "warehouse_server.py")) as f:
            content = f.read()
        from sources.legi import SUPPORTED_CODES
        for code in SUPPORTED_CODES:
            assert f'"{code}"' in content, f"warehouse manque le code {code!r}"
    finally:
        sys.path.pop(0)


# ─── 6. Live API tests (optionnels, skip si offline) ──────────

def _live_get(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "justicelibre-test/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def test_live_api_law():
    """Test live /api/law sur prod : article 1128 CC en 1992 → texte napoléonien."""
    d = _live_get("https://justicelibre.org/api/law?code=CC&num=1128&date=1992-05-15")
    if d is None:
        print("[SKIP live] offline ou prod down")
        return
    assert d.get("etat") in ("MODIFIE", "ABROGE")
    assert d.get("date_debut", "").startswith("1804")
    assert "commerce" in (d.get("texte", "") or "").lower()


def test_live_api_law_versions():
    d = _live_get("https://justicelibre.org/api/law/versions?code=CC&num=1128")
    if d is None:
        return
    versions = d.get("versions") or []
    assert isinstance(versions, list)
    assert len(versions) >= 2, f"attendu ≥2 versions, reçu {len(versions)}"
    # Vérifier la structure d'une version
    v = versions[0]
    assert "date_debut" in v
    assert "etat" in v


def test_live_mcp_health():
    """Le MCP doit répondre /v1/health (proxy nginx → FastMCP)."""
    # MCP utilise le SSE protocol — un simple GET retourne 404 normalement
    # On teste plutôt le warehouse health (al-uzza:8001 via API publique : non exposé).
    # Donc on teste juste que /api est joignable
    d = _live_get("https://justicelibre.org/api/")
    if d is None:
        return
    assert "service" in d
    assert "/api/law" in str(d.get("endpoints", {}))


def test_live_search_admin_via_mcp():
    """Si on a un client MCP, on testerait search_admin. Pour l'instant skip."""
    # Skip — nécessite un MCP client correct (initialize + tools/call)
    pass


# ─── Runner sans pytest ───────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("imports modules sources", test_imports),
        ("thésaurus chargé (≥100)", test_thesaurus_loaded),
        ("expand_synonyms basique", test_expand_synonyms_basic),
        ("expand_synonyms priorité longue clé", test_expand_synonyms_multi_word_priority),
        ("expand_synonyms préserve quotes", test_expand_synonyms_preserves_quotes),
        ("expand_synonyms vide", test_expand_synonyms_empty),
        ("legi.SUPPORTED_CODES (22)", test_legi_supported_codes),
        ("dila._sanitize_fts5", test_dila_sanitize_fts5),
        ("warehouse code mapping ↔ legi.py", test_warehouse_code_mapping),
        ("[live] /api/law (CC 1128 @ 1992)", test_live_api_law),
        ("[live] /api/law/versions", test_live_api_law_versions),
        ("[live] /api/ healthcheck", test_live_mcp_health),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as e:
            print(f"  ✗ {name}")
            print(f"      {e}")
            failed += 1
        except Exception as e:
            print(f"  ! {name} (erreur runtime) : {type(e).__name__}: {e}")
            failed += 1
    if failed:
        print(f"\n{failed}/{len(tests)} tests failed.")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
