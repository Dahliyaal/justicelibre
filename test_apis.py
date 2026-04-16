"""Sanity checks for the hidden APIs powering justicelibre.

Run: python3 test_apis.py

Goal: verify both data sources still respond, inspect response shapes,
and catch silent breakage before building the MCP server on top.
"""
import asyncio
import json
import httpx

JURIADMIN_BASE = "https://opendata.justice-administrative.fr/recherche/api"
ARIANE_URL = "https://www.conseil-etat.fr/xsearch"

SEARCH_QUERIES = [
    ("CE", "logement social"),
    ("CE", "référé liberté"),
    ("CE", "QPC"),
    ("CE-CAA", "urbanisme"),
    ("CE", "article 145"),
]


async def test_juriadmin_search(client: httpx.AsyncClient) -> None:
    print("=" * 60)
    print("JURIADMIN — model_search_juri")
    print("=" * 60)
    for juri, query in SEARCH_QUERIES:
        url = f"{JURIADMIN_BASE}/model_search_juri/openData/{juri}/{query}/5"
        r = await client.get(url)
        data = r.json()
        hits = data["decisions"]["body"]["hits"]
        total = hits["total"]["value"]
        docs = hits["hits"]
        print(f"[{r.status_code}] {juri} / {query!r} → {total} total, {len(docs)} returned")
        if docs:
            first = docs[0]["_source"]
            print(f"    first: {first.get('Numero_ECLI')} {first.get('Date_Lecture')} "
                  f"{first.get('Nom_Juridiction')}")


async def test_juriadmin_detail(client: httpx.AsyncClient) -> None:
    print()
    print("=" * 60)
    print("JURIADMIN — elastic/decisions detail (full text)")
    print("=" * 60)
    # First grab a recent decision id from the search endpoint
    r = await client.get(f"{JURIADMIN_BASE}/model_search_juri/openData/CE/urbanisme/1")
    hits = r.json()["decisions"]["body"]["hits"]["hits"]
    if not hits:
        print("  no decisions to fetch detail for")
        return
    ident = hits[0]["_source"]["Identification"]  # e.g. DCE_503506_20260409.xml
    decision_id = ident.rsplit(".xml", 1)[0]       # strip .xml suffix
    url = f"{JURIADMIN_BASE}/elastic/decisions/{decision_id}/bm9TZWNvbmR2YWx1ZQ=="
    r = await client.get(url)
    data = r.json()
    detail_hits = data["decisions"]["body"]["hits"]["hits"]
    print(f"[{r.status_code}] {decision_id} → {len(detail_hits)} hit(s)")
    if detail_hits:
        src = detail_hits[0]["_source"]
        para = src.get("paragraph", "")
        paragraphs = [p for p in para.split("$$$") if p.strip()]
        print(f"    ECLI: {src.get('Numero_ECLI')}")
        print(f"    fields: {list(src.keys())}")
        print(f"    paragraph length: {len(para)} chars, {len(paragraphs)} segments")
        if paragraphs:
            print(f"    first segment: {paragraphs[0][:200]}")


async def test_ariane(client: httpx.AsyncClient) -> None:
    print()
    print("=" * 60)
    print("ARIANE — Sinequa xsearch (Conseil d'État)")
    print("=" * 60)
    for _, query in SEARCH_QUERIES:
        params = {
            "type": "json",
            "SourceStr4": "AW_DCE",
            "text.add": query,
            "SkipCount": 0,
        }
        r = await client.get(ARIANE_URL, params=params)
        data = r.json()
        total = data.get("TotalCount", 0)
        docs = data.get("Documents", []) or []
        print(f"[{r.status_code}] {query!r} → {total} total, {len(docs)} returned")
        if docs:
            d = docs[0]
            title = d.get("Title") or d.get("Id")
            print(f"    first: rank={d.get('Rank')} relevance={d.get('Relevance')} "
                  f"id={d.get('Id')}")


async def main() -> None:
    timeout = httpx.Timeout(60.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        await test_juriadmin_search(client)
        await test_juriadmin_detail(client)
        await test_ariane(client)
    print()
    print("DONE.")


if __name__ == "__main__":
    asyncio.run(main())
