"""Échappement des séparateurs de ligne Unicode dans les trames JSON-RPC.

Certains textes DILA contiennent des U+0085 (NEL) bruts — mojibake cp1252
(0x85 = « … », les lignes pointillées des décisions) introduit en amont —
et rien n'exclut U+2028 (LINE SEPARATOR) / U+2029 (PARAGRAPH SEPARATOR).
JSON autorise ces trois caractères NON échappés dans une string, et
pydantic les sérialise tels quels ; mais côté client, les parseurs SSE qui
découpent le flux avec un splitlines() Unicode les traitent comme des fins
de ligne : la ligne `data:` est tronquée au milieu d'une string → « Failed
to parse SSE message: Invalid JSON: EOF while parsing a string ». Cas
d'école : CETATEXT000007543903 (CAA Nantes, 03NT00167) et ses 39 NEL
consécutifs, qui plantait get_decision_text / get_admin_decision.

Le SDK mcp (1.x comme 2.x, vérifié jusqu'à 2.0.0) n'offre aucun hook de
sérialisation et émet ces caractères bruts : les points d'émission
(streamable_http.py, sse.py, stdio) appellent tous `model_dump_json()`
sur les modèles JSON-RPC de mcp.types. On patche donc cette méthode pour
remplacer, dans le JSON déjà sérialisé, chaque occurrence brute par sa
séquence `\\uXXXX`. Transformation strictement équivalente : hors d'une
string, JSON ne peut contenir que de l'ASCII, donc ces caractères
n'apparaissent QUE dans des strings, où l'escape décode vers le même
caractère. Idempotent (le texte échappé est 100 % ASCII).

Cibles du patch selon la version du SDK :
- 1.x : JSONRPCMessage est un RootModel (enveloppe de toute réponse, y
  compris structuredContent) ; JSONRPCError est aussi émis directement
  par _create_error_response ;
- 2.x : JSONRPCMessage n'est plus qu'un alias d'union — le transport
  appelle model_dump_json() sur les instances concrètes. On patche donc
  les quatre classes membres (Request/Notification/Response/Error).
install() détecte la forme et patche tout ce qui existe ; patcher les
classes concrètes sous 1.x est inoffensif (escape idempotent).

Usage (avant le premier run du serveur) :
    import sse_escape
    sse_escape.install()
"""
from __future__ import annotations

import mcp.types as _mcp_types

_NEL = "\u0085"      # NEXT LINE (C1)
_LS = "\u2028"       # LINE SEPARATOR
_PS = "\u2029"       # PARAGRAPH SEPARATOR
_UNSAFE = (_NEL, _LS, _PS)


def escape_line_separators(serialized: str) -> str:
    """Remplace les séparateurs de ligne Unicode bruts d'un document JSON
    déjà sérialisé par leurs séquences d'échappement `\\uXXXX`."""
    if not any(ch in serialized for ch in _UNSAFE):
        return serialized
    return (
        serialized
        .replace(_NEL, "\\u0085")
        .replace(_LS, "\\u2028")
        .replace(_PS, "\\u2029")
    )


def _patch_targets() -> list[type]:
    """Classes JSON-RPC à patcher, selon la version du SDK (cf. docstring)."""
    targets = []
    for name in ("JSONRPCMessage", "JSONRPCRequest", "JSONRPCNotification",
                 "JSONRPCResponse", "JSONRPCError"):
        cls = getattr(_mcp_types, name, None)
        # En 2.x JSONRPCMessage est un alias d'union (pas une classe) : ignoré.
        if isinstance(cls, type) and hasattr(cls, "model_dump_json"):
            targets.append(cls)
    return targets


def install() -> None:
    """Applique le patch aux classes de mcp.types (une seule fois)."""
    for cls in _patch_targets():
        original = cls.model_dump_json
        if getattr(original, "_jl_sse_safe", False):
            continue

        def _make(orig):
            def model_dump_json(self, **kwargs):
                return escape_line_separators(orig(self, **kwargs))
            model_dump_json._jl_sse_safe = True
            return model_dump_json

        cls.model_dump_json = _make(original)
