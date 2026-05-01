"""Server-Side Rendering : pages HTML indexables par Google.

Génère du HTML statique à la volée pour chaque décision / article, avec
métadonnées propres (title, description, canonical, OpenGraph, JSON-LD).
Permet à Google d'indexer ~6.5M documents que le SPA seul ne pouvait pas
exposer (rendu différé du JS, pas de meta par route).

Cache HTTP : `Cache-Control: public, max-age=86400` → Cloudflare absorbe
les 99% de trafic après la première visite.

Routes câblées dans token_server.py :
  GET /decision/{source}/{id}  → SSR HTML décision
  GET /loi/{code}/{num}         → SSR HTML article de loi
  GET /sitemap.xml              → index sitemap (renvoie vers sub-sitemaps)
  GET /sitemap-{name}-{n}.xml   → sub-sitemap (50k URLs max)
  GET /robots.txt               → servi en statique par nginx
"""
from __future__ import annotations

import asyncio
import html
import re
import sqlite3
from pathlib import Path
from typing import Iterable

from search_api import fetch_decision
from sources import citations as _citations
from sources import warehouse as _wh

BASE_URL = "https://justicelibre.org"
SITE_NAME = "JusticeLibre"
DILA_DB = Path("/opt/justicelibre/dila/judiciaire.db")

SOURCE_LABELS = {
    "admin": "Justice administrative",
    "dila": "Justice judiciaire",
    "cedh": "Cour européenne des droits de l'homme",
    "cjue": "Cour de justice de l'Union européenne",
    "ariane": "Conseil d'État (ArianeWeb)",
}

# ─── Helpers ──────────────────────────────────────────────────────────

def esc(s: str) -> str:
    """HTML-escape pour interpolation dans un template."""
    return html.escape(s or "", quote=True)


def _strip(text: str, n: int = 200) -> str:
    """Premiers `n` caractères de texte propre pour <meta description>."""
    if not text:
        return ""
    t = re.sub(r"\s+", " ", text).strip()
    if len(t) <= n:
        return t
    return t[:n].rsplit(" ", 1)[0] + "…"


def _canonical(source: str, decision_id: str) -> str:
    return f"{BASE_URL}/decision/{source}/{decision_id}"


# ─── Decision page rendering ──────────────────────────────────────────

def render_decision(source: str, decision_id: str, data: dict) -> str:
    """Génère la page HTML SSR d'une décision."""
    juri = data.get("juridiction", "")
    date = data.get("date", "")
    numero = data.get("numero") or data.get("numero_dossier") or ""
    titre_brut = data.get("titre") or data.get("title") or ""
    text = data.get("text") or data.get("full_text") or data.get("paragraph") or ""
    ecli = data.get("ecli", "")
    formation = data.get("formation", "")
    solution = data.get("solution", "")
    nature = data.get("nature", "")

    # Titre canonique : "TA Lyon — n° 2200433 — 14 février 2023"
    parts = [p for p in [juri, f"n° {numero}" if numero else "", date] if p]
    title_h1 = " — ".join(parts) or titre_brut or f"Décision {decision_id}"
    title_seo = f"{title_h1} — {SITE_NAME}"

    # Description = début du texte (pour <meta> et OG)
    desc = _strip(text, 200) or f"{SOURCE_LABELS.get(source, '')} — {juri}".strip(" — ")

    canonical = _canonical(source, decision_id)
    # Maillage interne : transforme chaque "art. L.X-Y du code Z" en
    # <a href="/loi/Z/LX-Y">. Crucial pour le crawl Google : les bots
    # peuvent maintenant naviguer décision → article → autres décisions.
    text_linked = _citations.linkify(text, esc)
    text_html = "<p>" + text_linked.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"

    # JSON-LD Schema.org : LegalCase / Article. Aide les LLM et rich snippets.
    jsonld = {
        "@context": "https://schema.org",
        "@type": ["LegalCase", "CreativeWork"],
        "name": title_h1,
        "headline": title_h1,
        "url": canonical,
        "datePublished": date or None,
        "creator": {"@type": "GovernmentOrganization", "name": juri} if juri else None,
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": BASE_URL},
        "inLanguage": "fr",
        "license": "https://www.etalab.gouv.fr/licence-ouverte-open-licence",
        "identifier": ecli or numero or decision_id,
    }
    jsonld_clean = {k: v for k, v in jsonld.items() if v is not None}
    import json as _json
    jsonld_str = esc(_json.dumps(jsonld_clean, ensure_ascii=False))

    meta_rows = []
    if juri: meta_rows.append(("Juridiction", esc(juri)))
    if date: meta_rows.append(("Date", esc(date)))
    if numero: meta_rows.append(("Numéro", esc(numero)))
    if ecli: meta_rows.append(("ECLI", esc(ecli)))
    if formation: meta_rows.append(("Formation", esc(formation)))
    if nature: meta_rows.append(("Nature", esc(nature)))
    if solution: meta_rows.append(("Solution", esc(solution)))
    meta_html = "".join(
        f'<tr><th>{k}</th><td>{v}</td></tr>' for k, v in meta_rows
    )

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title_seo)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canonical)}">
<link rel="icon" type="image/svg+xml" href="/logo.svg">
<meta property="og:type" content="article">
<meta property="og:title" content="{esc(title_h1)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:locale" content="fr_FR">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{esc(title_h1)}">
<meta name="twitter:description" content="{esc(desc)}">
<script type="application/ld+json">{jsonld_str}</script>
<style>
body{{font-family:-apple-system,system-ui,Segoe UI,Roboto,sans-serif;max-width:780px;margin:0 auto;padding:2rem 1.2rem 4rem;color:#1a1a1a;line-height:1.6}}
header{{border-bottom:1px solid #e0ddd6;padding-bottom:1rem;margin-bottom:1.5rem}}
.crumb{{font-size:.85rem;color:#6b6b6b;margin-bottom:.5rem}}
.crumb a{{color:#1a4e4e;text-decoration:none}}
h1{{font-family:Georgia,serif;font-size:1.8rem;line-height:1.3;margin:.5rem 0}}
.meta-table{{width:100%;border-collapse:collapse;font-size:.9rem;margin:1rem 0 2rem}}
.meta-table th{{text-align:left;color:#6b6b6b;font-weight:500;padding:.3rem 1rem .3rem 0;width:30%;vertical-align:top}}
.meta-table td{{padding:.3rem 0;vertical-align:top}}
article{{font-size:1rem;color:#3a3a3a}}
article p{{margin:0 0 1em}}
footer{{margin-top:3rem;padding-top:1.5rem;border-top:1px solid #e0ddd6;font-size:.85rem;color:#6b6b6b}}
footer a{{color:#1a4e4e}}
.cta{{display:inline-block;margin-top:1rem;padding:.6rem 1.2rem;background:#1a4e4e;color:#fff;text-decoration:none;border-radius:4px;font-size:.9rem}}
</style>
</head>
<body>
<header>
  <div class="crumb"><a href="/">JusticeLibre</a> &rsaquo; <a href="/search.html">Recherche</a> &rsaquo; {esc(SOURCE_LABELS.get(source, source))}</div>
  <h1>{esc(title_h1)}</h1>
</header>
<table class="meta-table">{meta_html}</table>
<article>{text_html}</article>
<footer>
  <p>Document publié sous <a href="https://www.etalab.gouv.fr/licence-ouverte-open-licence">Licence Ouverte 2.0</a> — accès libre via <a href="/">JusticeLibre</a>, alternative open source à Doctrine/Légifrance pour l'accès à la jurisprudence française et européenne.</p>
  <p><a class="cta" href="/search.html">Rechercher d'autres décisions</a></p>
</footer>
</body>
</html>"""


def render_law(code: str, num: str, data: dict) -> str:
    """Page HTML SSR d'un article de loi avec JSON-LD Legislation."""
    titre_section = data.get("titre_section", "")
    texte = data.get("texte", "") or ""
    etat = data.get("etat", "")
    date_debut = data.get("date_debut", "")
    date_fin = data.get("date_fin", "")
    nota = data.get("nota", "") or ""
    source_url = data.get("source_url", "")
    legitext = data.get("legitext", "")
    legiarti = data.get("legiarti", "")

    # Titre canonique : "Article L262-8 du Code de l'action sociale et des familles"
    h1 = f"Article {num} {('— ' + titre_section) if titre_section and titre_section != 'Code' else f'du {code}'}"
    title_seo = f"Article {num} {code} — JusticeLibre"

    desc = _strip(texte, 200) or f"Article {num} du {titre_section or code}"
    canonical = f"{BASE_URL}/loi/{code}/{num}"

    text_html = "<p>" + esc(texte).replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
    nota_html = f'<aside class="nota"><strong>Note :</strong> {esc(nota)}</aside>' if nota else ""

    jsonld = {
        "@context": "https://schema.org",
        "@type": "Legislation",
        "name": h1,
        "headline": h1,
        "url": canonical,
        "legislationIdentifier": legiarti or num,
        "legislationJurisdiction": "FR",
        "datePublished": date_debut or None,
        "expires": date_fin if date_fin and date_fin != "2999-01-01" else None,
        "inLanguage": "fr",
        "license": "https://www.etalab.gouv.fr/licence-ouverte-open-licence",
        "isPartOf": {"@type": "Legislation", "name": titre_section or code},
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": BASE_URL},
        "legislationLegalForce": "InForce" if etat == "VIGUEUR" else "PartiallyInForce",
    }
    jsonld_clean = {k: v for k, v in jsonld.items() if v is not None}
    import json as _json
    jsonld_str = esc(_json.dumps(jsonld_clean, ensure_ascii=False))

    meta_rows = [("État", esc(etat)), ("Code", esc(titre_section or code))]
    if date_debut: meta_rows.append(("En vigueur depuis", esc(date_debut)))
    if date_fin and date_fin != "2999-01-01": meta_rows.append(("Jusqu'au", esc(date_fin)))
    meta_html = "".join(
        f'<tr><th>{k}</th><td>{v}</td></tr>' for k, v in meta_rows
    )

    legifrance_btn = (
        f'<a href="{esc(source_url)}" rel="external nofollow">Voir sur Légifrance</a>'
        if source_url else ""
    )

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title_seo)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canonical)}">
<link rel="icon" type="image/svg+xml" href="/logo.svg">
<meta property="og:type" content="article">
<meta property="og:title" content="{esc(h1)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:locale" content="fr_FR">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{esc(h1)}">
<meta name="twitter:description" content="{esc(desc)}">
<script type="application/ld+json">{jsonld_str}</script>
<style>
body{{font-family:-apple-system,system-ui,Segoe UI,Roboto,sans-serif;max-width:780px;margin:0 auto;padding:2rem 1.2rem 4rem;color:#1a1a1a;line-height:1.6}}
header{{border-bottom:1px solid #e0ddd6;padding-bottom:1rem;margin-bottom:1.5rem}}
.crumb{{font-size:.85rem;color:#6b6b6b;margin-bottom:.5rem}}
.crumb a{{color:#1a4e4e;text-decoration:none}}
h1{{font-family:Georgia,serif;font-size:1.6rem;line-height:1.3;margin:.5rem 0}}
.meta-table{{width:100%;border-collapse:collapse;font-size:.9rem;margin:1rem 0 2rem}}
.meta-table th{{text-align:left;color:#6b6b6b;font-weight:500;padding:.3rem 1rem .3rem 0;width:30%;vertical-align:top}}
.meta-table td{{padding:.3rem 0;vertical-align:top}}
article{{font-size:1rem;color:#3a3a3a}}
article p{{margin:0 0 1em}}
.nota{{font-size:.9rem;background:#f5f5f3;padding:1rem;border-left:3px solid #1a4e4e;margin:2rem 0}}
footer{{margin-top:3rem;padding-top:1.5rem;border-top:1px solid #e0ddd6;font-size:.85rem;color:#6b6b6b}}
footer a{{color:#1a4e4e}}
.cta{{display:inline-block;margin-top:1rem;padding:.6rem 1.2rem;background:#1a4e4e;color:#fff;text-decoration:none;border-radius:4px;font-size:.9rem;margin-right:.5rem}}
.cta.alt{{background:transparent;color:#1a4e4e;border:1px solid #1a4e4e}}
</style>
</head>
<body>
<header>
  <div class="crumb"><a href="/">JusticeLibre</a> &rsaquo; <a href="/search.html">Lois et codes</a> &rsaquo; {esc(titre_section or code)}</div>
  <h1>{esc(h1)}</h1>
</header>
<table class="meta-table">{meta_html}</table>
<article>{text_html}{nota_html}</article>
<footer>
  <p>Article publié sous <a href="https://www.etalab.gouv.fr/licence-ouverte-open-licence">Licence Ouverte 2.0</a> via <a href="/">JusticeLibre</a> — accès libre au droit français.</p>
  <p>
    <a class="cta" href="/search.html?q={esc(num)}">Décisions citant cet article</a>
    <a class="cta alt" href="/api/law/versions?code={esc(code)}&num={esc(num)}">Historique des versions</a>
    {legifrance_btn}
  </p>
</footer>
</body>
</html>"""


def render_law_404(code: str, num: str) -> str:
    return f"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8">
<title>Article {esc(code)} {esc(num)} introuvable — {SITE_NAME}</title>
<meta name="robots" content="noindex">
</head><body style="font-family:sans-serif;max-width:600px;margin:3rem auto;padding:1rem">
<h1>Article introuvable</h1>
<p>L'article <code>{esc(num)}</code> du <code>{esc(code)}</code> n'a pas été trouvé.</p>
<p>Vérifie le code (CC, CT, CJA, CASF…) et le numéro (sans points : <code>R772-8</code>, pas <code>R.772-8</code>).</p>
<p><a href="/search.html">Recherche libre</a></p>
</body></html>"""


def render_decision_404(source: str, decision_id: str) -> str:
    return f"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8">
<title>Décision introuvable — {SITE_NAME}</title>
<meta name="robots" content="noindex">
</head><body style="font-family:sans-serif;max-width:600px;margin:3rem auto;padding:1rem">
<h1>Décision introuvable</h1>
<p>Aucune décision avec l'identifiant <code>{esc(decision_id)}</code> dans la source <code>{esc(source)}</code>.</p>
<p><a href="/search.html">Rechercher dans la base</a></p>
</body></html>"""


# ─── Sitemap generation ───────────────────────────────────────────────

STATIC_PAGES = [
    ("/", "1.0", "weekly"),
    ("/search.html", "0.9", "weekly"),
    ("/tutoriel-piste.html", "0.6", "monthly"),
    ("/stats.html", "0.4", "weekly"),
]


SITEMAP_PAGE_SIZE = 50000


def render_sitemap_index() -> str:
    """Index des sitemaps (l'unique fichier que tu soumets à Search Console).

    Annonce :
    - 1 sitemap statique (landing, search, tutoriel, stats)
    - N sub-sitemaps DILA (Cass + CA + CC, ~225k)
    - N sub-sitemaps JADE (CE + 9 CAA + 40 TA, ~4M, via warehouse)
    - N sub-sitemaps LEGI (articles de loi en vigueur, ~1.5M, via warehouse)
    """
    sub = [f"{BASE_URL}/sitemap-static.xml"]
    # DILA local SQLite
    try:
        with sqlite3.connect(f"file:{DILA_DB}?mode=ro", uri=True) as c:
            total = c.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        n_pages = (total // SITEMAP_PAGE_SIZE) + 1
        for i in range(1, n_pages + 1):
            sub.append(f"{BASE_URL}/sitemap-dila-{i}.xml")
    except Exception:
        pass
    # JADE distant warehouse (CE + 9 CAA admin)
    try:
        total_jade = _wh.sync_count_fond("jade")
        if total_jade > 0:
            n_pages = (total_jade // SITEMAP_PAGE_SIZE) + 1
            for i in range(1, n_pages + 1):
                sub.append(f"{BASE_URL}/sitemap-jade-{i}.xml")
    except Exception:
        pass
    # CEDH local PROD (~76k, 1 page)
    try:
        with sqlite3.connect(f"file:{DILA_DB}?mode=ro", uri=True) as c:
            n = c.execute("SELECT COUNT(*) FROM cedh_decisions").fetchone()[0]
        for i in range(1, (n // SITEMAP_PAGE_SIZE) + 2):
            sub.append(f"{BASE_URL}/sitemap-cedh-{i}.xml")
    except Exception:
        pass
    # CJUE local PROD (~44k, 1 page)
    try:
        with sqlite3.connect(f"file:{DILA_DB}?mode=ro", uri=True) as c:
            n = c.execute("SELECT COUNT(*) FROM cjue_decisions").fetchone()[0]
        for i in range(1, (n // SITEMAP_PAGE_SIZE) + 2):
            sub.append(f"{BASE_URL}/sitemap-cjue-{i}.xml")
    except Exception:
        pass
    # ArianeWeb CE local PROD (~60k, 1-2 pages)
    try:
        with sqlite3.connect(f"file:{DILA_DB}?mode=ro", uri=True) as c:
            n = c.execute("SELECT COUNT(*) FROM ariane_decisions").fetchone()[0]
        for i in range(1, (n // SITEMAP_PAGE_SIZE) + 2):
            sub.append(f"{BASE_URL}/sitemap-ariane-{i}.xml")
    except Exception:
        pass
    # CNIL délibérations al-uzza (~26k, 1 page)
    try:
        total_cnil = _wh.sync_count_fond("cnil")
        if total_cnil > 0:
            for i in range(1, (total_cnil // SITEMAP_PAGE_SIZE) + 2):
                sub.append(f"{BASE_URL}/sitemap-cnil-{i}.xml")
    except Exception:
        pass
    # LEGI distant warehouse (articles de loi VIGUEUR — laissés indexables
    # même si moins prioritaires : permettent à Google de comprendre les
    # citations internes des décisions et d'indexer les articles.
    try:
        total_legi = _wh.sync_count_fond("legi")
        if total_legi > 0:
            n_pages = (total_legi // SITEMAP_PAGE_SIZE) + 1
            for i in range(1, n_pages + 1):
                sub.append(f"{BASE_URL}/sitemap-legi-{i}.xml")
    except Exception:
        pass

    items = "\n".join(f"  <sitemap><loc>{u}</loc></sitemap>" for u in sub)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{items}
</sitemapindex>"""


def render_sitemap_jade(page: int, page_size: int = SITEMAP_PAGE_SIZE) -> str:
    """Sub-sitemap JADE (admin), trié par date DESC. `page` 1-indexed."""
    if page < 1:
        page = 1
    offset = (page - 1) * page_size
    rows = _wh.sync_enumerate_fond("jade", offset=offset, limit=page_size)
    items = "\n".join(
        f'  <url><loc>{BASE_URL}/decision/admin/{esc(r.get("id",""))}</loc>'
        f'<lastmod>{esc(r.get("date") or "")}</lastmod></url>'
        for r in rows if r.get("id")
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{items}
</urlset>"""


def render_sitemap_cedh(page: int = 1, page_size: int = SITEMAP_PAGE_SIZE) -> str:
    """Sub-sitemap CEDH (~76k). Lit la table cedh_decisions de PROD."""
    if page < 1: page = 1
    offset = (page - 1) * page_size
    rows = []
    try:
        with sqlite3.connect(f"file:{DILA_DB}?mode=ro", uri=True) as c:
            rows = c.execute(
                "SELECT itemid, date FROM cedh_decisions ORDER BY date DESC LIMIT ? OFFSET ?",
                (page_size, offset),
            ).fetchall()
    except Exception:
        pass
    items = "\n".join(
        f'  <url><loc>{BASE_URL}/decision/cedh/{esc(rid)}</loc>'
        f'<lastmod>{esc(d) if d else ""}</lastmod></url>'
        for rid, d in rows if rid
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{items}
</urlset>"""


def render_sitemap_cjue(page: int = 1, page_size: int = SITEMAP_PAGE_SIZE) -> str:
    """Sub-sitemap CJUE (~44k). Lit la table cjue_decisions de PROD."""
    if page < 1: page = 1
    offset = (page - 1) * page_size
    rows = []
    try:
        with sqlite3.connect(f"file:{DILA_DB}?mode=ro", uri=True) as c:
            rows = c.execute(
                "SELECT celex, date FROM cjue_decisions ORDER BY date DESC LIMIT ? OFFSET ?",
                (page_size, offset),
            ).fetchall()
    except Exception:
        pass
    items = "\n".join(
        f'  <url><loc>{BASE_URL}/decision/cjue/{esc(rid)}</loc>'
        f'<lastmod>{esc(d) if d else ""}</lastmod></url>'
        for rid, d in rows if rid
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{items}
</urlset>"""


def render_sitemap_ariane(page: int = 1, page_size: int = SITEMAP_PAGE_SIZE) -> str:
    """Sub-sitemap ArianeWeb CE (~60k). ariane_decisions n'a pas de date,
    on utilise fetched_at comme proxy lastmod."""
    if page < 1: page = 1
    offset = (page - 1) * page_size
    rows = []
    try:
        with sqlite3.connect(f"file:{DILA_DB}?mode=ro", uri=True) as c:
            rows = c.execute(
                "SELECT ariane_id, fetched_at FROM ariane_decisions "
                "ORDER BY ariane_num DESC LIMIT ? OFFSET ?",
                (page_size, offset),
            ).fetchall()
    except Exception:
        pass
    items = []
    for rid, ts in rows:
        if not rid:
            continue
        # ariane_id ressemble à "/Ariane_Web/AW_DCE/|497566" — on URL-encode
        # simplement le path tel qu'attendu par fetch_decision(source=ariane).
        from urllib.parse import quote
        slug = quote(rid, safe="")
        lastmod = (ts or "")[:10] if ts else ""
        items.append(
            f'  <url><loc>{BASE_URL}/decision/ariane/{esc(slug)}</loc>'
            f'<lastmod>{esc(lastmod)}</lastmod></url>'
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(items)}
</urlset>"""


def render_sitemap_cnil(page: int = 1, page_size: int = SITEMAP_PAGE_SIZE) -> str:
    """Sub-sitemap CNIL délibérations (~26k). Via warehouse al-uzza."""
    if page < 1: page = 1
    offset = (page - 1) * page_size
    rows = _wh.sync_enumerate_fond("cnil", offset=offset, limit=page_size)
    items = "\n".join(
        f'  <url><loc>{BASE_URL}/decision/cnil/{esc(r.get("id",""))}</loc>'
        f'<lastmod>{esc(r.get("date") or "")}</lastmod></url>'
        for r in rows if r.get("id")
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{items}
</urlset>"""


def render_sitemap_legi(page: int, page_size: int = SITEMAP_PAGE_SIZE) -> str:
    """Sub-sitemap LEGI (articles de loi VIGUEUR). URL = /loi/{code}/{num}.

    On utilise le LEGITEXT du parent comme pseudo-code si pas de mapping
    inverse disponible — sinon Google va essayer d'indexer une URL invalide.
    Pour LEGI, l'enumerate retourne (id=legiarti, legitext, num, date).
    On a besoin du code court (CC, CT, CASF…) pour matcher CODE_TO_LEGITEXT
    côté warehouse.
    """
    if page < 1:
        page = 1
    offset = (page - 1) * page_size
    rows = _wh.sync_enumerate_fond("legi", offset=offset, limit=page_size)
    # Mapping LEGITEXT → code court (lazy import pour éviter cycles)
    from sources import legi as _legi
    LEGITEXT_TO_CODE = {v: k for k, v in _legi.SUPPORTED_CODES_LEGITEXT.items()} \
        if hasattr(_legi, "SUPPORTED_CODES_LEGITEXT") else {}
    items_list = []
    for r in rows:
        legitext = r.get("legitext") or ""
        num = r.get("num") or ""
        if not legitext or not num:
            continue
        code = LEGITEXT_TO_CODE.get(legitext)
        if not code:
            # Fallback : utiliser le LEGITEXT directement comme code
            # (warehouse_server.law_at_date accepte LEGITEXT* en input)
            code = legitext
        items_list.append(
            f'  <url><loc>{BASE_URL}/loi/{esc(code)}/{esc(num)}</loc>'
            f'<lastmod>{esc(r.get("date") or "")}</lastmod></url>'
        )
    items = "\n".join(items_list)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{items}
</urlset>"""


def render_sitemap_static() -> str:
    items = "\n".join(
        f'  <url><loc>{BASE_URL}{path}</loc><priority>{prio}</priority><changefreq>{freq}</changefreq></url>'
        for path, prio, freq in STATIC_PAGES
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{items}
</urlset>"""


def render_sitemap_dila(page: int, page_size: int = 50000) -> str:
    """Sub-sitemap DILA (Cass + CA + CC), trié par date DESC.
    `page` est 1-indexed.
    """
    if page < 1:
        page = 1
    offset = (page - 1) * page_size
    rows = []
    try:
        with sqlite3.connect(f"file:{DILA_DB}?mode=ro", uri=True) as c:
            cur = c.execute(
                "SELECT id, date FROM decisions ORDER BY date DESC LIMIT ? OFFSET ?",
                (page_size, offset),
            )
            rows = cur.fetchall()
    except Exception:
        rows = []
    items = "\n".join(
        f'  <url><loc>{BASE_URL}/decision/dila/{esc(rid)}</loc>'
        f'<lastmod>{esc(d) if d else ""}</lastmod></url>'
        for rid, d in rows
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{items}
</urlset>"""


# ─── Sync wrappers (token_server is sync HTTPServer) ──────────────────

def fetch_decision_sync(source: str, decision_id: str) -> dict | None:
    try:
        return asyncio.run(fetch_decision(source=source, decision_id=decision_id))
    except Exception:
        return None
