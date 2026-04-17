"""Probe Legifrance PISTE API to understand structure for scraping."""
import httpx
import json
import os
from pathlib import Path as _P

_f = _P(__file__).with_name(".env")
if _f.exists():
    for _line in _f.read_text().splitlines():
        if "=" in _line and not _line.strip().startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())
CLIENT_ID = os.environ.get("PISTE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("PISTE_CLIENT_SECRET", "")

r = httpx.post("https://oauth.piste.gouv.fr/api/oauth/token", data={
    "grant_type": "client_credentials",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "scope": "openid",
})
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}", "accept": "application/json", "Content-Type": "application/json"}

base = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"

# Test ping
r = httpx.get(f"{base}/consult/ping", headers=h, timeout=20)
print("ping:", r.status_code, r.text[:100])

# List codes
body = {"sort": "CODE_DATE_MAJ", "pageSize": 5, "pageNumber": 1, "states": ["VIGUEUR"]}
r = httpx.post(f"{base}/list/code", json=body, headers=h, timeout=30)
print("\nPOST /list/code:", r.status_code)
if r.status_code == 200:
    d = r.json()
    print(f"  total: {d.get('totalResultNumber')}, first results:")
    for c in d.get("results", [])[:5]:
        cid = c.get("cid", "?")
        titre = c.get("titre", c.get("titreTxt", "?"))
        print(f"    {cid}: {titre}")
else:
    print(r.text[:500])

# Consult a specific code — Code civil, cid = LEGITEXT000006070721
body = {"textId": "LEGITEXT000006070721"}
r = httpx.post(f"{base}/consult/code", json=body, headers=h, timeout=30)
print("\nPOST /consult/code (Code civil):", r.status_code)
if r.status_code == 200:
    d = r.json()
    print(f"  keys: {list(d.keys())[:10]}")
    sections = d.get("sections", [])
    print(f"  top-level sections: {len(sections)}")
    for s in sections[:3]:
        print(f"    - {s.get('id', '?')}: {s.get('title', '?')}")
else:
    print(r.text[:500])

# Try to get an article directly
body = {"id": "LEGIARTI000006419292"}  # article 9 Code civil (vie privée)
r = httpx.post(f"{base}/consult/getArticle", json=body, headers=h, timeout=30)
print("\nPOST /consult/getArticle (Art.9 CC):", r.status_code)
if r.status_code == 200:
    d = r.json()
    art = d.get("article", {})
    print(f"  id: {art.get('id')}, num: {art.get('num')}")
    text = art.get("texte", art.get("texteHtml", ""))[:200]
    print(f"  text[0:200]: {text}")
else:
    print(r.text[:500])
