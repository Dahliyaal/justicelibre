#!/usr/bin/env python3
"""Serveur de prévisualisation LOCAL de la v2 (3/10/2026).

Sert web/ en statique, et génère à la volée, avec ssr_v2, les pages
/loi/<code>/<num> et /decision/<source>/<id> à partir de l'API publique de
justicelibre.org. Les liens de la v2 restent ainsi sur localhost au lieu de
partir vers les pages en ligne (v1). Lecture seule, pour le développement.

    python3 scripts/dev_v2_server.py 8787
"""
import http.server
import json
import os
import sys
import urllib.parse
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
import ssr_v2  # noqa: E402

API = "https://justicelibre.org"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "jl-dev-v2"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=os.path.join(RACINE, "web"), **k)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _html(self, code, html):
        b = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        parts = [urllib.parse.unquote(p) for p in u.path.split("/") if p]
        q = urllib.parse.parse_qs(u.query)
        try:
            if len(parts) == 3 and parts[0] == "loi":
                code, num = parts[1], parts[2]
                url = f"{API}/api/law?code={urllib.parse.quote(code)}&num={urllib.parse.quote(num)}"
                if q.get("date"):
                    url += "&date=" + urllib.parse.quote(q["date"][0])
                return self._html(200, ssr_v2.render_law(code, num, _get(url)))
            if len(parts) == 3 and parts[0] == "decision":
                src, did = parts[1], parts[2]
                url = f"{API}/api/decision?source={urllib.parse.quote(src)}&id={urllib.parse.quote(did, safe='')}"
                return self._html(200, ssr_v2.render_decision(src, did, _get(url)))
        except Exception as e:  # pragma: no cover - outil de dev
            return self._html(502, f"<p>Prévisualisation v2 : erreur {e!r}</p>")
        return super().do_GET()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
