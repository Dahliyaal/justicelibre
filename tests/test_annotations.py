"""Test suite for MCP tool annotations.

Locks down that every tool registered on the FastMCP server carries the
safety annotations required by MCP clients (and by Anthropic's Connectors
Directory review) : a human-readable `title` and `readOnlyHint: true`.
The server is read-only by design — a new tool that writes data must set
`destructiveHint` instead, and this test must be updated accordingly.

Run :
    python3 -m pytest tests/test_annotations.py -v
ou :
    python3 tests/test_annotations.py
"""
import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import server  # noqa: E402


def _list_tools():
    return asyncio.run(server.mcp.list_tools())


def test_every_tool_has_annotations():
    missing = [t.name for t in _list_tools() if t.annotations is None]
    assert not missing, "tools sans annotations :\n  " + "\n  ".join(missing)


def test_every_tool_has_title():
    missing = [
        t.name for t in _list_tools()
        if not (t.annotations and (t.annotations.title or "").strip())
    ]
    assert not missing, "tools sans title :\n  " + "\n  ".join(missing)


def test_every_tool_is_read_only():
    # Le serveur n'expose que de la consultation. Tout nouveau tool qui
    # écrit doit porter destructiveHint et être exclu explicitement ici.
    wrong = [
        t.name for t in _list_tools()
        if not (t.annotations and t.annotations.readOnlyHint is True)
    ]
    assert not wrong, "tools sans readOnlyHint=True :\n  " + "\n  ".join(wrong)


# ─── Runner sans pytest ──────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("every tool has annotations", test_every_tool_has_annotations),
        ("every tool has a title",     test_every_tool_has_title),
        ("every tool is read-only",    test_every_tool_is_read_only),
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
    if failed:
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
