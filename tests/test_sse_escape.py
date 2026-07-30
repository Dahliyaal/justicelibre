"""Test de régression : séparateurs de ligne Unicode dans les trames MCP.

Bug d'origine (30 juillet 2026) : CETATEXT000007543903 (CAA Nantes,
n° 03NT00167) contient 39 U+0085 (NEL) consécutifs — mojibake cp1252 des
lignes pointillées « ……… ». JSON les autorise bruts dans une string et
pydantic les émet tels quels, mais les parseurs SSE côté client qui
découpent le flux avec un splitlines() Unicode y voient des fins de ligne :
la ligne `data:` est tronquée au milieu d'une string → « Failed to parse
SSE message: Invalid JSON: EOF while parsing a string ». Plantait
get_decision_text et get_admin_decision sur ce record.

Vérifie (OFFLINE, sans base ni réseau) que le patch sse_escape :
  1. supprime tout U+0085/U+2028/U+2029 brut des trames sérialisées
     (enveloppe JSON-RPC, structuredContent inclus, et JSONRPCError) ;
  2. est LOSSLESS : le JSON décodé restitue les caractères à l'identique ;
  3. laisse une trame qui survit à un découpage splitlines() Unicode
     (simulation du parseur SSE client) ;
  4. est idempotent (double install(), double passage d'escape).

Run :
    python3 tests/test_sse_escape.py
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import sse_escape  # noqa: E402
import mcp.types as mcp_types  # noqa: E402

NEL, LS, PS = "\u0085", "\u2028", "\u2029"
UNSAFE = (NEL, LS, PS)

# Reproduction du payload fautif : run de NEL entre deux paragraphes,
# comme dans le full_text de CETATEXT000007543903.
HOSTILE = (
    "…une somme de 1 500 euros au titre de l'article L.761-1 ;\n\n"
    + NEL * 39
    + "\n\nVu les autres pièces du dossier ;"
    + LS + "ligne après LS" + PS + "paragraphe après PS"
)


def _frame(result: dict) -> str:
    """Sérialise un résultat de tool comme le fait streamable_http.py."""
    msg = mcp_types.JSONRPCMessage(
        root=mcp_types.JSONRPCResponse(jsonrpc="2.0", id=2, result=result)
    )
    return msg.model_dump_json(by_alias=True, exclude_none=True)


def main() -> None:
    sse_escape.install()
    sse_escape.install()  # idempotence de l'install

    # 1. Trame réponse : structuredContent + content text, tous deux
    # porteurs du texte hostile.
    inner = json.dumps({"id": "CETATEXT000007543903", "full_text": HOSTILE},
                       ensure_ascii=False, indent=2)
    frame = _frame({
        "content": [{"type": "text", "text": inner}],
        "structuredContent": {"full_text": HOSTILE},
        "isError": False,
    })
    for ch in UNSAFE:
        assert ch not in frame, f"U+{ord(ch):04X} brut dans la trame"

    # 2. Lossless : le décodage JSON restitue le texte à l'identique.
    decoded = json.loads(frame)
    assert decoded["result"]["structuredContent"]["full_text"] == HOSTILE
    assert json.loads(decoded["result"]["content"][0]["text"])["full_text"] == HOSTILE

    # 3. Simulation du parseur SSE client : la ligne `data:` doit rester
    # entière même sous un splitlines() Unicode (qui coupe sur NEL/LS/PS).
    sse = f"event: message\r\ndata: {frame}\r\n\r\n"
    data_lines = [l for l in sse.splitlines() if l.startswith("data: ")]
    assert len(data_lines) == 1, "la trame se fait découper par splitlines()"
    json.loads(data_lines[0][6:])  # doit parser sans EOF

    # 4. Idempotence de l'escape : repasser une trame déjà échappée ne
    # change rien (elle est 100 % exempte de caractères bruts).
    assert sse_escape.escape_line_separators(frame) == frame

    # 5. Chemin JSONRPCError (émis directement par _create_error_response).
    err = mcp_types.JSONRPCError(
        jsonrpc="2.0", id="server-error",
        error=mcp_types.ErrorData(code=-32600, message="texte" + NEL + "coupé"),
    )
    s = err.model_dump_json(by_alias=True, exclude_none=True)
    assert NEL not in s and "\\u0085" in s
    assert json.loads(s)["error"]["message"] == "texte" + NEL + "coupé"

    print("✓ test_sse_escape : trames MCP sans séparateur de ligne Unicode brut, roundtrip lossless")


if __name__ == "__main__":
    main()
