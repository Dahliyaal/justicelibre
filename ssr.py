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

from functools import lru_cache

from search_api import fetch_decision
from sources import citations as _citations
from sources import warehouse as _wh


@lru_cache(maxsize=20000)
def _cached_law_url(code: str, num: str, date: str) -> str | None:
    """LRU cache mémoire des résolutions article→URL Légifrance.

    Les mêmes articles (L262-8 CASF, R411-1 CJA…) sont cités dans des
    milliers de décisions. Sans cache : 1 lookup HTTP warehouse par article
    par décision = 250-500ms cumulés → CloudFlare 502 quand >5s.
    Avec cache : 1ère décision paye, les suivantes sont gratuites.
    """
    try:
        row = _wh.sync_get_law(code, num, date or None)
        return row.get("source_url") if row else None
    except Exception:
        return None


_PCJA_CODE_RE = __import__('re').compile(r'\b(\d{1,3}(?:-\d{1,3}){2,5})(?:,\s*(RJ\d+|FXH))?\s+', flags=__import__('re').UNICODE)
_RENVOIS_RE = __import__('re').compile(r'(?:^|\s)(\d+\.\s+(?:Cf\.|Rappr\.|Comp\.|V\.\s+aussi|Voir))', flags=__import__('re').UNICODE)


def _clean_dila_text(t: str) -> str:
    """Nettoie le texte stocké en DB des artefacts XML/HTML résiduels.

    Le parser DILA laisse parfois passer des `<br/>`, `&amp;`, etc. Si on
    laisse, le navigateur affiche la balise littérale après html.escape.
    On les remplace par des séparateurs naturels en amont.
    """
    if not t:
        return ""
    import html as _html
    # 1. Décoder les entités déjà présentes (au cas où double-encodées)
    t = _html.unescape(t)
    # 2. Remplacer les balises HTML résiduelles par des espaces/retours
    t = __import__('re').sub(r'<\s*br\s*/?\s*>', '\n', t, flags=__import__('re').IGNORECASE)
    t = __import__('re').sub(r'<\s*p\s*/?\s*>', '\n\n', t, flags=__import__('re').IGNORECASE)
    t = __import__('re').sub(r'<[^>]+>', '', t)  # autres tags : strip
    # 3. Collapse multiples retours
    t = __import__('re').sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def _render_legal_text(text: str, esc, resolve, sommaire: str = "") -> str:
    """Rend le texte d'une décision en HTML structuré.

    3 cas :
      1. Sommaire séparé fourni + texte intégral → texte intégral en haut,
         puis sections "Plan de classement / Résumé / Renvois" sous le texte.
      2. Pas de sommaire séparé, texte court qui commence par code PCJA
         (vieux arrêt pré-numérisation) → on splitte le texte en sections.
      3. Texte intégral classique sans analyses → rendu paragraphes simple.
    """
    if not text and not sommaire:
        return "<p><em>Texte indisponible.</em></p>"

    # Détection « vieux arrêt » : texte court (<3000 ch) qui commence par un code PCJA
    is_old_summary = (text and len(text) < 3000 and bool(_PCJA_CODE_RE.match(text)))

    # Si text == sommaire (cas où DILA a juste recopié le sommaire dans la balise
    # texte faute de texte intégral disponible) : on ne rend que la version
    # structurée pour éviter le doublon.
    if text and sommaire and (text.strip() == sommaire.strip() or text.strip() in sommaire.strip()):
        return _split_sommaire_sections(sommaire, esc, resolve)

    # Cas 1 : texte intégral + sommaire séparé fourni
    if text and sommaire and not is_old_summary:
        text_linked = _citations.linkify(text, esc, url_resolver=resolve)
        body = "<p>" + text_linked.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
        # Découpe le sommaire en abstrats / résumé / renvois (même logique que vieux arrêts)
        sections_html = _split_sommaire_sections(sommaire, esc, resolve)
        return body + sections_html

    if is_old_summary:
        return _split_sommaire_sections(text, esc, resolve)

    # Cas 3 général (arrêt avec texte intégral seulement) : rendu paragraphes
    text_linked = _citations.linkify(text, esc, url_resolver=resolve)
    return "<p>" + text_linked.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"


def _split_sommaire_sections(text: str, esc, resolve) -> str:
    """Découpe un sommaire/analyse en 3 sections : Plan de classement, Résumé, Renvois."""
    parts = {"abstrats": "", "resume": "", "renvois": ""}
    # Split sur "1. Cf." pour isoler les renvois jurisprudentiels
    m_renvois = _RENVOIS_RE.search(text)
    if m_renvois:
        parts["renvois"] = text[m_renvois.start():].strip()
        text = text[:m_renvois.start()].strip()
    # Split sur premier passage en casse mixte (analyses MAJUSCULES → résumé Mixte)
    import re as _re
    m_resume = _re.search(r'(\d{1,3}(?:-\d{1,3}){2,5}(?:,\s*\d{1,3}(?:-\d{1,3}){2,5})*\s+)([A-ZÉÈÀÂÊÎÔÛÇ][a-zéèàâêîôûç])', text)
    if m_resume:
        parts["abstrats"] = text[:m_resume.start(2)].strip()
        parts["resume"] = text[m_resume.start(2):].strip()
    else:
        parts["abstrats"] = text.strip()
    out = []
    if parts["abstrats"]:
        out.append('<section class="legal-section">')
        out.append('<h3>Plan de classement</h3>')
        out.append(f'<div class="abstrats">{esc(parts["abstrats"])}</div>')
        out.append('</section>')
    if parts["resume"]:
        text_resume_linked = _citations.linkify(parts["resume"], esc, url_resolver=resolve)
        out.append('<section class="legal-section">')
        out.append('<h3>Résumé</h3>')
        out.append(f'<p>{text_resume_linked}</p>')
        out.append('</section>')
    if parts["renvois"]:
        out.append('<section class="legal-section">')
        out.append('<h3>Renvois jurisprudentiels</h3>')
        out.append(f'<p>{esc(parts["renvois"])}</p>')
        out.append('</section>')
    return "\n".join(out)


def _official_source_button(decision_id: str) -> str:
    """Génère le HTML du gros bouton CTA 'Voir sur source officielle'."""
    pat = _official_source_from_pattern(decision_id)
    if not pat:
        return ""
    label, url = pat
    return (
        '<div class="source-cta">'
        '<a class="btn-source" href="' + url + '" target="_blank" rel="external noopener nofollow">'
        '<span class="btn-source-label">Voir sur ' + label + '</span>'
        '<span class="btn-source-arrow">→</span>'
        '</a>'
        '<small>Cette décision est aussi disponible sur la source publique officielle. '
        'JusticeLibre est une copie miroir indexée pour les moteurs de recherche et les IA.</small>'
        '</div>'
    )


def _official_source_from_pattern(decision_id: str) -> tuple[str, str] | None:
    """Devine l'URL source officielle à partir du pattern de l'ID.

    Retourne (label_court_pour_bouton, url) ou None si pattern non reconnu.

    Patterns supportés (vérifiés en base) :
      - CETATEXT*   → Légifrance/ceta (Conseil d'État + JADE)
      - JURITEXT*   → Légifrance/juri (Cour de cassation)
      - CONSTEXT*   → Légifrance/jorf (Conseil constitutionnel)
      - DCE_/DCAA_/DTA_*  → opendata.justice-administrative.fr (admin récents)
      - 001-*       → HUDOC (Cour EDH)
      - ECLI:EU:* / *CELEX*  → EUR-Lex (CJUE)
    """
    if not decision_id:
        return None
    if decision_id.startswith("CETATEXT"):
        return ("Légifrance", f"https://www.legifrance.gouv.fr/ceta/id/{decision_id}")
    if decision_id.startswith("JURITEXT"):
        return ("Légifrance", f"https://www.legifrance.gouv.fr/juri/id/{decision_id}")
    if decision_id.startswith("CONSTEXT"):
        return ("Légifrance", f"https://www.legifrance.gouv.fr/cons/id/{decision_id}")
    if decision_id.startswith("001-"):
        return ("HUDOC -CEDH", f"https://hudoc.echr.coe.int/eng?i={decision_id}")
    if decision_id.startswith("ECLI:EU:"):
        return ("EUR-Lex", f"https://eur-lex.europa.eu/legal-content/FR/TXT/?uri={decision_id}")
    # CELEX brut ou avec préfixe : 5 chiffres + 2 lettres + 4 chiffres (ex 62025CC0121, 62021TJ0109)
    import re as _re
    if _re.match(r"^\d{4,5}[A-Z]{2}\d{4}$", decision_id) or "CELEX" in decision_id:
        celex = decision_id.replace("CELEX:", "").replace("CELEX", "")
        return ("EUR-Lex", f"https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:{celex}")
    # TA / CAA / CE récents : opendata deep-link ne fonctionne pas (page JS shell).
    # Fallback search Légifrance par numéro (peut retourner la décision si Lebon).
    m = _re.match(r"^(?:DCE|DCAA|DTA|ORTA)_([0-9A-Z]+)_", decision_id)
    if m:
        return ("Légifrance (recherche)",
                f"https://www.legifrance.gouv.fr/search/all?query={m.group(1)}&fonds=cetat")
    return None


@lru_cache(maxsize=20000)
def _cached_decision_url(decision_id: str, date: str) -> str | None:
    """Résout decision_id → URL source officielle.

    Stratégie : pattern local d'abord (rapide, jamais d'erreur réseau),
    puis fallback warehouse si pattern non reconnu (cas exotique).
    """
    pat = _official_source_from_pattern(decision_id)
    if pat:
        return pat[1]
    try:
        return _wh.sync_build_url(decision_id, date=date or None)
    except Exception:
        return None

BASE_URL = "https://justicelibre.org"
SITE_NAME = "JusticeLibre"
DILA_DB = Path("/opt/justicelibre/dila/judiciaire.db")

SOURCE_LABELS = {
    "admin": "Justice administrative",
    "dila": "Justice judiciaire",
    "cedh": "Cour européenne des droits de l'homme",
    "cjue": "Cour de justice de l'Union européenne",
    "ariane": "Conseil d'État (ArianeWeb)",
    "cnil": "CNIL",
}

# Origine de la donnée bulk pour chaque source. Important pour la confiance :
# montre d'où vient l'info (vs un site « AI slop » qui invente des décisions).
# Affiché dans la meta-table sous "Source de l'archive".
BULK_SOURCES = {
    "admin":  ("DILA -bulk JADE",
               "https://echanges.dila.gouv.fr/OPENDATA/JADE/"),
    "dila":   ("DILA -bulks CASS / CAPP / CONSTIT",
               "https://echanges.dila.gouv.fr/OPENDATA/CASS/"),
    "cedh":   ("HUDOC -Cour européenne des droits de l'homme",
               "https://hudoc.echr.coe.int/"),
    "cjue":   ("InforCuria -CJUE",
               "https://curia.europa.eu/jcms/jcms/j_6/fr/"),
    "ariane": ("ArianeWeb -Conseil d'État",
               "https://www.conseil-etat.fr/arianeweb/"),
    "cnil":   ("DILA -bulk CNIL délibérations",
               "https://echanges.dila.gouv.fr/OPENDATA/CNIL/"),
}

# ─── Composants partagés (reproduits du SPA pour cohérence visuelle) ───
# Ces blocs HTML/CSS sont une copie simplifiée du <head> + topbar de
# web/search.html. Toute mise à jour visuelle du SPA doit être répercutée
# ici pour que les pages SSR ne dépareillent pas.

GOOGLE_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=DM+Serif+Display:ital@0;1&'
    'family=DM+Sans:ital,opsz,wght@0,9..40,300..800;1,9..40,300..800&'
    'family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">'
)

SHARED_CSS = """
:root{
  --teal:#1a4e4e;--teal-l:#2a6b6b;--teal-xl:#e8f0f0;
  --gold:#b8932b;
  --ink:#1a1a1a;--body:#3a3a3a;--muted:#6b6b6b;
  --light:#f5f5f3;--white:#ffffff;--line:#e0ddd6;
  --display:"DM Serif Display",Georgia,serif;
  --sans:"DM Sans",-apple-system,BlinkMacSystemFont,sans-serif;
  --mono:"JetBrains Mono",Menlo,Consolas,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{min-height:100%}
body{font-family:var(--sans);font-size:15px;color:var(--ink);background:var(--light);
  -webkit-font-smoothing:antialiased;display:flex;flex-direction:column;min-height:100vh}
a{color:var(--teal);text-decoration:none}
a:hover{text-decoration:underline}
::selection{background:var(--teal);color:#fff}
/* Topbar (copié de search.html) */
.topbar{
  position:sticky;top:0;z-index:100;background:rgba(255,255,255,.96);backdrop-filter:blur(8px);
  display:flex;align-items:center;justify-content:space-between;
  padding:.85rem 2.5rem;border-bottom:1px solid var(--line);
}
.logo-area{display:flex;align-items:center;gap:.8rem}
.logo-area img{width:44px;height:44px}
.logo-area .name{font-family:var(--display);font-size:1.1rem;color:var(--ink)}
.logo-area .name .tld{color:var(--teal)}
.proto-badge{display:inline-block;margin-left:.65rem;font-size:.58rem;font-weight:700;
  letter-spacing:.15em;text-transform:uppercase;padding:.18rem .45rem;
  border:1px solid var(--gold);color:var(--gold);border-radius:2px;
  vertical-align:middle;cursor:help;}
nav.main-nav{display:flex;align-items:center;gap:2rem}
nav.main-nav a{font-size:.78rem;font-weight:600;text-transform:uppercase;letter-spacing:.12em;
  color:var(--ink);padding-bottom:.4rem;border-bottom:3px solid transparent}
nav.main-nav a:hover{border-bottom-color:var(--teal);text-decoration:none}
@media(max-width:860px){nav.main-nav a:not(.active){display:none}}
/* Theme toggle button (synchronisé avec search.html) */
.theme-toggle{
  background:none;border:1px solid var(--line);
  width:34px;height:34px;border-radius:50%;
  cursor:pointer;display:flex;align-items:center;justify-content:center;
  color:var(--muted);transition:color .2s,border-color .2s;
}
.theme-toggle:hover{color:var(--teal);border-color:var(--teal)}
.theme-toggle svg{width:16px;height:16px}
html[data-theme="dark"] .theme-toggle .sun{display:block}
html[data-theme="dark"] .theme-toggle .moon{display:none}
html:not([data-theme="dark"]) .theme-toggle .sun{display:none}
html:not([data-theme="dark"]) .theme-toggle .moon{display:block}
@media (prefers-color-scheme: dark){
  html:not([data-theme="light"]) .theme-toggle .sun{display:block}
  html:not([data-theme="light"]) .theme-toggle .moon{display:none}
}
/* Dark mode pour le contenu SSR (synchronisé avec search.html) */
html[data-theme="dark"]{
  --ink:#e8e8e6;--body:#c4c4c0;--muted:#9a9a96;
  --light:#1e1e1c;--white:#2a2a28;--line:#3a3a36;
  --teal:#4ea0a0;--teal-l:#6bb5b5;--teal-xl:#1a3030;
  --gold:#d4b050;
}
html[data-theme="dark"] body{background:var(--light)}
html[data-theme="dark"] .topbar{background:rgba(30,30,28,.96)}
@media (prefers-color-scheme: dark){
  html:not([data-theme="light"]){
    --ink:#e8e8e6;--body:#c4c4c0;--muted:#9a9a96;
    --light:#1e1e1c;--white:#2a2a28;--line:#3a3a36;
    --teal:#4ea0a0;--teal-l:#6bb5b5;--teal-xl:#1a3030;
  }
  html:not([data-theme="light"]) body{background:var(--light)}
  html:not([data-theme="light"]) .topbar{background:rgba(30,30,28,.96)}
}
/* Conteneur principal */
.wrap{max-width:820px;margin:0 auto;padding:2.5rem 1.5rem 5rem;flex:1;width:100%}
/* Sub-bar (analogue de .searchbar du SPA, contient le fil d'ariane) */
.page-subbar{
  background:var(--white);border-bottom:1px solid var(--line);
  padding:.85rem 2.5rem;display:flex;align-items:center;gap:1rem;justify-content:space-between;
}
.page-subbar .crumb{font-size:.75rem;color:var(--muted);text-transform:uppercase;
  letter-spacing:.12em;font-weight:600}
.page-subbar .crumb a{color:var(--muted)}
.page-subbar .crumb a:hover{color:var(--teal)}
.page-subbar .return{font-size:.78rem;color:var(--teal);font-weight:600}
.page-subbar .return:hover{text-decoration:underline}
/* Title block */
.kicker{font-size:.78rem;color:var(--teal);font-weight:600;text-transform:uppercase;
  letter-spacing:.15em;margin-bottom:.6rem}
h1{font-family:var(--display);font-size:2.2rem;line-height:1.15;color:var(--ink);
  font-weight:400;margin-bottom:.3rem}
h1 em{color:var(--teal);font-style:italic}
.subline{color:var(--muted);font-size:.95rem;margin-bottom:2rem}
/* Meta table */
.meta-table{width:100%;border-collapse:collapse;font-size:.88rem;
  margin:1.5rem 0 2.5rem;background:var(--white);border:1px solid var(--line);border-radius:6px}
.meta-table th{text-align:left;color:var(--muted);font-weight:500;
  padding:.55rem 1rem;width:30%;vertical-align:top;border-bottom:1px solid var(--line)}
.meta-table td{padding:.55rem 1rem;vertical-align:top;color:var(--ink);border-bottom:1px solid var(--line)}
.meta-table tr:last-child th,.meta-table tr:last-child td{border-bottom:0}
.meta-table .source-row{background:var(--teal-xl)}
.meta-table .source-row a{font-weight:600}
/* CTA Source officielle */
.source-cta{display:flex;flex-direction:column;align-items:flex-start;gap:.5rem;
  margin:1.5rem 0 0;padding:1.1rem 1.4rem;background:var(--teal-xl);
  border-left:4px solid var(--teal);border-radius:0 6px 6px 0}
.btn-source{display:inline-flex;align-items:center;gap:.6rem;
  background:var(--teal);color:#fff!important;padding:.7rem 1.3rem;
  border-radius:4px;font-weight:600;font-size:.95rem;text-decoration:none;
  transition:background .15s ease}
.btn-source:hover{background:var(--teal-l)}
.btn-source-arrow{font-size:1.1em;line-height:1}
.source-cta small{font-size:.78rem;color:var(--muted);line-height:1.45;font-style:italic}
/* Article body */
article{font-size:1rem;color:var(--body);background:var(--white);line-height:1.6;
  padding:2rem;border:1px solid var(--line);border-radius:6px}
article p{margin:0 0 1em}
article p:last-child{margin-bottom:0}
/* Sections analytiques (vieux arrêts pré-numérisation : abstrats + résumé + renvois) */
.legal-section{margin:0 0 1.5em;padding:0}
.legal-section + .legal-section{padding-top:1em;border-top:1px solid var(--line)}
.legal-section h3{font-family:var(--display);font-size:1.05rem;font-weight:400;color:var(--teal);
  margin:0 0 .6em;padding:0}
.legal-section .abstrats{font-size:.88rem;line-height:1.55;color:var(--body);
  background:var(--cream);padding:.9em 1.1em;border-left:2px solid var(--line);border-radius:0 4px 4px 0;
  white-space:pre-wrap;font-family:var(--sans)}
.legal-section p{margin:0}
.wrap, .wrap p, .wrap .subline{line-height:1.5}
.lawref{color:var(--teal);text-decoration:underline;text-decoration-color:rgba(26,78,78,.3);
  text-underline-offset:.15em}
.lawref:hover{text-decoration-color:var(--teal)}
.lawref.external::after{content:" ↗";font-size:.8em;color:var(--muted)}
/* Nota */
.nota{font-size:.9rem;background:var(--teal-xl);padding:1rem 1.2rem;
  border-left:3px solid var(--teal);margin:1.5rem 0;color:var(--ink)}
.nota strong{color:var(--teal)}
/* Footer */
footer.page-footer{margin-top:3rem;padding-top:1.5rem;border-top:1px solid var(--line);
  font-size:.85rem;color:var(--muted)}
footer.page-footer a{color:var(--teal)}
.cta-row{display:flex;gap:.6rem;flex-wrap:wrap;margin-top:1rem}
.cta{display:inline-block;padding:.6rem 1.2rem;background:var(--teal);color:#fff;
  border-radius:4px;font-size:.85rem;text-decoration:none}
.cta:hover{background:var(--teal-l);text-decoration:none}
.cta.alt{background:transparent;color:var(--teal);border:1px solid var(--teal)}
.cta.alt:hover{background:var(--teal-xl)}
"""

# Source de vérité unique : on extrait le <header class="topbar">…</header>
# de search.html à chaque render (avec mémo léger 60s pour ne pas re-lire
# le fichier à chaque requête). Si jamais on touche au topbar dans
# search.html, le SSR se met à jour automatiquement -> plus de drift.
SEARCH_HTML_PATH = Path("/var/www/justicelibre/search.html")
_TOPBAR_CACHE: dict = {"html": None, "loaded_at": 0.0}
_TOPBAR_TTL = 60.0  # secondes, suffit pour propager les MAJ

_TOPBAR_FALLBACK = """<header class="topbar">
  <a href="/" class="logo-area">
    <img src="/logo.svg" alt="">
    <span class="name">justicelibre<span class="tld">.org</span></span>
    <span class="proto-badge" title="Version bêta">bêta</span>
  </a>
  <nav class="main-nav">
    <a href="/">Accueil</a>
    <a href="/search.html">Recherche</a>
    <a href="/#connect">MCP</a>
    <a href="https://github.com/Dahliyaal/justicelibre">GitHub</a>
  </nav>
</header>"""


def get_topbar_html() -> str:
    """Lit le <header class=\"topbar\">…</header> depuis search.html.

    Cache 60s. Strip l'attribut `active` du lien Recherche (ne s'applique
    pas aux pages SSR décision/loi).
    """
    import time as _time
    now = _time.time()
    if _TOPBAR_CACHE["html"] and (now - _TOPBAR_CACHE["loaded_at"] < _TOPBAR_TTL):
        return _TOPBAR_CACHE["html"]
    html_str = _TOPBAR_FALLBACK
    try:
        if SEARCH_HTML_PATH.exists():
            content = SEARCH_HTML_PATH.read_text(encoding="utf-8")
            m = re.search(r'<header class="topbar">.*?</header>', content, re.DOTALL)
            if m:
                extracted = m.group(0)
                # Retire la class "active" (le lien est actif sur /search.html
                # mais pas sur les pages décision/loi servies en SSR).
                extracted = extracted.replace(' class="active"', '')
                html_str = extracted
    except Exception:
        pass
    _TOPBAR_CACHE["html"] = html_str
    _TOPBAR_CACHE["loaded_at"] = now
    return html_str


# Petit JS pour wire le bouton theme-toggle de la topbar (sync avec search.html).
# Inline en bas des pages SSR pour éviter une round-trip + protéger des
# erreurs si le bouton n'existe pas (defensive null check).
THEME_JS = """<script>
(function(){
  // Init: theme stocké, sinon hérite du système (sans set explicite)
  var saved = localStorage.getItem('jl-theme');
  if (saved) document.documentElement.dataset.theme = saved;
  var btn = document.getElementById('themeToggle');
  if (!btn) return;
  btn.addEventListener('click', function(){
    var h = document.documentElement;
    var cur = h.dataset.theme;
    if (!cur) {
      // pas de choix explicite: bascule à l'opposé du système
      cur = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    var nxt = cur === 'dark' ? 'light' : 'dark';
    h.dataset.theme = nxt;
    localStorage.setItem('jl-theme', nxt);
  });
})();
</script>"""


# Compat avec le code existant qui référence TOPBAR_HTML comme constante.
# Note: cette ligne est résolue au moment de l'import. Pour avoir la version
# fraîche à chaque render, le code utilise désormais get_topbar_html().
TOPBAR_HTML = get_topbar_html()

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
    """Génère la page HTML SSR d'une décision (style cohérent avec le SPA).

    Le résolveur de citations est optionnel mais activé par défaut : pour
    chaque article cité dans le texte, on essaie de fetch l'URL Légifrance
    dated/officielle (sync_get_law). Linkifiable en target=_blank.
    """
    juri = data.get("juridiction", "")
    date = data.get("date", "")
    numero = data.get("numero") or data.get("numero_dossier") or ""
    titre_brut = data.get("titre") or data.get("title") or ""
    text = data.get("text") or data.get("full_text") or data.get("paragraph") or ""
    sommaire = data.get("sommaire") or ""  # analyses PCJA + résumé (Lebon-style)
    ecli = data.get("ecli", "")
    formation = data.get("formation", "")
    solution = data.get("solution", "")
    nature = data.get("nature", "")

    # Titre H1 : juridiction en kicker, le n° + date en gros
    main_id = f"n° {numero}" if numero else titre_brut or f"Décision {decision_id}"
    title_h1 = main_id
    if date:
        title_h1 = f"{main_id} <em>· {esc(_format_fr_date(date))}</em>"
    title_h1_plain = f"{main_id} · {_format_fr_date(date)}" if date else main_id
    title_seo = f"{juri or main_id}, {numero or ''} {(_format_fr_date(date) or '').strip()} -{SITE_NAME}".strip()

    desc = _strip(text, 200) or f"{SOURCE_LABELS.get(source, '')} -{juri}".strip(" -")
    canonical = _canonical(source, decision_id)

    # Source officielle de la décision (Légifrance, opendata, hudoc, eur-lex)
    source_url = _cached_decision_url(decision_id, date or "") if decision_id else None

    # Citations dans le texte → pré-fetch parallèle pour éviter timeout CloudFlare
    # quand la décision cite 20+ articles (cas typique des grosses décisions Cass/Constit).
    cited = _citations.detect_citations(text)  # [(code, num, span)]
    if cited:
        from concurrent.futures import ThreadPoolExecutor
        unique_keys = {(c, n) for (c, n, _) in cited}
        # parallélise jusqu'à 16 lookups simultanés (réseau bound, pas CPU)
        with ThreadPoolExecutor(max_workers=min(16, len(unique_keys))) as ex:
            list(ex.map(lambda kn: _cached_law_url(kn[0], kn[1], date or ""), unique_keys))
    # Maintenant tout est en cache LRU mémoire → linkify est instantané
    def _resolve(code: str, num: str) -> str | None:
        return _cached_law_url(code, num, date or "")
    # Nettoyage texte source : élimine les balises HTML brutes stockées en DB
    # (artefact du parsing XML DILA qui laisse passer <br/>, &lt;br&gt; etc.)
    # avant escape, sinon le navigateur affiche la balise littérale.
    text = _clean_dila_text(text)
    sommaire = _clean_dila_text(sommaire)
    # Si on a déjà tout dans `text` (cas vieux arrêts pré-numérisation : text
    # = analyses + résumé concaténés) : structurer le bloc.
    # Si on a `text` ET `sommaire` séparés (cas standard JADE) : afficher
    # les deux en sections distinctes.
    text_html = _render_legal_text(text, esc, _resolve, sommaire=sommaire)

    jsonld = {
        "@context": "https://schema.org",
        "@type": ["LegalCase", "CreativeWork"],
        "name": title_h1_plain,
        "headline": title_h1_plain,
        "url": canonical,
        "datePublished": date or None,
        "creator": {"@type": "GovernmentOrganization", "name": juri} if juri else None,
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": BASE_URL},
        "inLanguage": "fr",
        "license": "https://www.etalab.gouv.fr/licence-ouverte-open-licence",
        "identifier": ecli or numero or decision_id,
        "sameAs": source_url or None,
    }
    jsonld_clean = {k: v for k, v in jsonld.items() if v is not None}
    import json as _json
    jsonld_str = esc(_json.dumps(jsonld_clean, ensure_ascii=False))

    rows = []
    if juri: rows.append(("Juridiction", esc(juri)))
    if date: rows.append(("Date", esc(_format_fr_date(date))))
    if numero: rows.append(("Numéro", esc(numero)))
    if ecli: rows.append(("ECLI", f'<code>{esc(ecli)}</code>'))
    if formation: rows.append(("Formation", esc(formation)))
    if nature: rows.append(("Nature", esc(nature)))
    if solution: rows.append(("Solution", esc(solution)))
    meta_html = "".join(
        f'<tr><th>{k}</th><td>{v}</td></tr>' for k, v in rows
    )
    if source_url:
        meta_html += (
            f'<tr class="source-row"><th>Source officielle</th>'
            f'<td><a href="{esc(source_url)}" target="_blank" rel="external noopener">'
            f'{_source_host(source_url)} ↗</a></td></tr>'
        )
    bulk_label, bulk_url = BULK_SOURCES.get(source, ("", ""))
    if bulk_url:
        meta_html += (
            f'<tr class="source-row"><th>Source de l\'archive</th>'
            f'<td><a href="{esc(bulk_url)}" target="_blank" rel="external noopener">'
            f'{esc(bulk_label)} ↗</a></td></tr>'
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
<meta property="og:title" content="{esc(title_h1_plain)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:locale" content="fr_FR">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{esc(title_h1_plain)}">
<meta name="twitter:description" content="{esc(desc)}">
<script type="application/ld+json">{jsonld_str}</script>
{GOOGLE_FONTS}
<style>{SHARED_CSS}</style>
</head>
<body>
{get_topbar_html()}
<div class="page-subbar">
  <div class="crumb"><a href="/">Accueil</a> &nbsp;›&nbsp; <a href="/search.html">Recherche</a> &nbsp;›&nbsp; {esc(SOURCE_LABELS.get(source, source))}</div>
</div>
<main class="wrap">
  <div class="kicker">{esc(juri or SOURCE_LABELS.get(source, ''))}</div>
  <h1>{title_h1}</h1>
  <p class="subline">Décision rendue par {esc(juri or 'la juridiction')}{', le ' + esc(_format_fr_date(date)) if date else ''}.</p>
  {_official_source_button(decision_id)}
  <table class="meta-table">{meta_html}</table>
  <article>{text_html}</article>
  <footer class="page-footer">
    <p>Document juridique publié sous <a href="https://www.etalab.gouv.fr/licence-ouverte-open-licence" rel="noopener">Licence Ouverte 2.0</a>. Accès libre via <strong>JusticeLibre</strong> -alternative open source à Doctrine, Lexis et Légifrance pour la jurisprudence française et européenne.</p>
  </footer>
</main>
{THEME_JS}
</body>
</html>"""


def _format_fr_date(iso: str) -> str:
    """`2023-02-14` → `14 février 2023`. Robuste à des formats variés."""
    if not iso or len(iso) < 7:
        return iso or ""
    months_fr = ["janvier","février","mars","avril","mai","juin",
                 "juillet","août","septembre","octobre","novembre","décembre"]
    try:
        y, m, *rest = iso.split("-")
        d = rest[0] if rest else ""
        mi = int(m) - 1
        if 0 <= mi < 12:
            return f"{int(d) if d else ''} {months_fr[mi]} {y}".strip()
    except Exception:
        pass
    return iso


def _source_host(url: str) -> str:
    """Affiche un nom de domaine lisible pour le bouton source."""
    if not url: return ""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc
        host = host.removeprefix("www.")
        return host
    except Exception:
        return url[:30]


def render_law(code: str, num: str, data: dict) -> str:
    """Page HTML SSR d'un article de loi (style cohérent avec le SPA)."""
    titre_section = data.get("titre_section", "")
    texte = data.get("texte", "") or ""
    etat = data.get("etat", "")
    date_debut = data.get("date_debut", "")
    date_fin = data.get("date_fin", "")
    nota = data.get("nota", "") or ""
    source_url = data.get("source_url", "")
    legitext = data.get("legitext", "")
    legiarti = data.get("legiarti", "")

    code_label = titre_section or code
    title_h1 = f"Article {num}"
    title_seo = f"Article {num} -{code_label} -{SITE_NAME}"
    desc = _strip(texte, 200) or f"Article {num} du {code_label}"
    canonical = f"{BASE_URL}/loi/{code}/{num}"

    text_html = "<p>" + esc(texte).replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
    nota_html = f'<aside class="nota"><strong>Note :</strong> {esc(nota)}</aside>' if nota else ""

    jsonld = {
        "@context": "https://schema.org",
        "@type": "Legislation",
        "name": f"{title_h1} -{code_label}",
        "headline": title_h1,
        "url": canonical,
        "legislationIdentifier": legiarti or num,
        "legislationJurisdiction": "FR",
        "datePublished": date_debut or None,
        "expires": date_fin if date_fin and date_fin != "2999-01-01" else None,
        "inLanguage": "fr",
        "license": "https://www.etalab.gouv.fr/licence-ouverte-open-licence",
        "isPartOf": {"@type": "Legislation", "name": code_label},
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": BASE_URL},
        "legislationLegalForce": "InForce" if etat == "VIGUEUR" else "PartiallyInForce",
        "sameAs": source_url or None,
    }
    jsonld_clean = {k: v for k, v in jsonld.items() if v is not None}
    import json as _json
    jsonld_str = esc(_json.dumps(jsonld_clean, ensure_ascii=False))

    rows = [("Code", esc(code_label)), ("État", esc(etat or "-"))]
    if date_debut: rows.append(("En vigueur depuis", esc(_format_fr_date(date_debut))))
    if date_fin and date_fin != "2999-01-01":
        rows.append(("Jusqu'au", esc(_format_fr_date(date_fin))))
    if legiarti: rows.append(("Identifiant", f'<code>{esc(legiarti)}</code>'))
    meta_html = "".join(
        f'<tr><th>{k}</th><td>{v}</td></tr>' for k, v in rows
    )
    if source_url:
        meta_html += (
            f'<tr class="source-row"><th>Source officielle</th>'
            f'<td><a href="{esc(source_url)}" target="_blank" rel="external noopener">'
            f'{_source_host(source_url)} ↗</a></td></tr>'
        )
    # Bulk LEGI pour les articles de loi (toujours pareil)
    meta_html += (
        '<tr class="source-row"><th>Source de l\'archive</th>'
        '<td><a href="https://echanges.dila.gouv.fr/OPENDATA/LEGI/" '
        'target="_blank" rel="external noopener">'
        'DILA -bulk LEGI (codes consolidés) ↗</a></td></tr>'
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
<meta property="og:title" content="{esc(title_h1 + ' -' + code_label)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:locale" content="fr_FR">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{esc(title_h1 + ' -' + code_label)}">
<meta name="twitter:description" content="{esc(desc)}">
<script type="application/ld+json">{jsonld_str}</script>
{GOOGLE_FONTS}
<style>{SHARED_CSS}</style>
</head>
<body>
{get_topbar_html()}
<div class="page-subbar">
  <div class="crumb"><a href="/">Accueil</a> &nbsp;›&nbsp; <a href="/search.html">Recherche</a> &nbsp;›&nbsp; {esc(code_label)}</div>
</div>
<main class="wrap">
  <div class="kicker">{esc(code_label)}</div>
  <h1>Article <em>{esc(num)}</em></h1>
  <p class="subline">Article{(' en vigueur depuis le ' + _format_fr_date(date_debut)) if date_debut else ''}.</p>
  <table class="meta-table">{meta_html}</table>
  <article>{text_html}{nota_html}</article>
  <footer class="page-footer">
    <p>Article de loi publié sous <a href="https://www.etalab.gouv.fr/licence-ouverte-open-licence" rel="noopener">Licence Ouverte 2.0</a> via <strong>JusticeLibre</strong>.</p>
  </footer>
</main>
{THEME_JS}
</body>
</html>"""


def render_law_404(code: str, num: str) -> str:
    return f"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8">
<title>Article {esc(code)} {esc(num)} introuvable -{SITE_NAME}</title>
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
<title>Décision introuvable -{SITE_NAME}</title>
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
    # Opendata progressivement crawlé (TAs + CAA + CE complets)
    try:
        total_od = _wh.sync_count_fond("opendata")
        if total_od > 0:
            n_pages = (total_od // SITEMAP_PAGE_SIZE) + 1
            for i in range(1, n_pages + 1):
                sub.append(f"{BASE_URL}/sitemap-opendata-{i}.xml")
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
    # LEGI distant warehouse (articles de loi VIGUEUR -laissés indexables
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
        # ariane_id ressemble à "/Ariane_Web/AW_DCE/|497566" -on URL-encode
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


def render_sitemap_opendata(page: int = 1, page_size: int = SITEMAP_PAGE_SIZE) -> str:
    """Sub-sitemap opendata.justice-administrative.fr (TAs + CAA + CE).
    Le DL est progressif (cf download_opendata.py) : ce sub-sitemap reflète
    l'état courant à chaque appel. Cache 1h pour suivre la croissance.
    """
    if page < 1: page = 1
    offset = (page - 1) * page_size
    rows = _wh.sync_enumerate_fond("opendata", offset=offset, limit=page_size)
    items = "\n".join(
        f'  <url><loc>{BASE_URL}/decision/admin/{esc(r.get("id",""))}</loc>'
        f'<lastmod>{esc(r.get("date") or "")}</lastmod></url>'
        for r in rows if r.get("id")
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{items}
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
    inverse disponible -sinon Google va essayer d'indexer une URL invalide.
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
