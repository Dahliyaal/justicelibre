"""Aucun code inatteignable dans le dépôt.

Pourquoi ce fichier existe (23 août 2026) : l'ajout de l'alias `id` sur
`get_decision_judiciaire` (16 août) avait été inséré AU MILIEU de la
branche `session_token`. Le bloc `async with _client()` qui appelait
réellement l'API PISTE s'est retrouvé APRÈS un `return` — donc jamais
exécuté. Effet : un utilisateur muni d'un jeton PISTE **valide** recevait
« L'accès via PISTE requiert une authentification OAuth2 », c'est-à-dire
qu'on lui demandait de s'authentifier alors qu'il venait de le faire.

Python n'émet aucun avertissement pour ça, aucun test ne le voyait (le
chemin PISTE n'est pas testable sans jeton), et le message d'erreur
paraissait sensé. Un `ast` de trois lignes l'attrape en une seconde.

Run :
    python3 tests/test_no_dead_code.py
"""
import ast
import os
import pathlib
import sys

_HERE = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
_ROOT = _HERE.parent

# Un statement placé après l'un de ceux-ci, dans le même bloc, est mort.
_TERMINATORS = (ast.Return, ast.Raise, ast.Continue, ast.Break)
_SKIP_DIRS = {".git", "__pycache__", "node_modules", "prototypes"}


def _unreachable(path: pathlib.Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []          # fichier non parsable : hors périmètre, pas un échec
    out = []
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if not isinstance(block, list):
                continue
            for i, stmt in enumerate(block[:-1]):
                if isinstance(stmt, _TERMINATORS):
                    nxt = block[i + 1]
                    out.append(
                        f"{path.relative_to(_ROOT)}:{nxt.lineno} — "
                        f"{type(nxt).__name__} après {type(stmt).__name__} "
                        f"(ligne {stmt.lineno})")
    return out


def test_pas_de_code_inatteignable():
    dead = []
    for path in sorted(_ROOT.rglob("*.py")):
        if _SKIP_DIRS & set(path.parts):
            continue
        dead.extend(_unreachable(path))
    assert not dead, (
        "code inatteignable — un bloc placé après un return/raise ne "
        "s'exécutera JAMAIS :\n      " + "\n      ".join(dead))


if __name__ == "__main__":
    try:
        test_pas_de_code_inatteignable()
    except AssertionError as e:
        print(f"  ✗ {e}")
        sys.exit(1)
    print("  ✓ aucun code inatteignable\n\nAll 1 tests passed.")
