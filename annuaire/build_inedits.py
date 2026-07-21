#!/usr/bin/env python3
"""Génère l'écosystème /inedits.* : adresses email scrapées depuis PDF gouv.

Structure (comme /annuaire.html) :
- /inedits.html                    : index + petites catégories inline + cards vers sous-pages
- /inedits/<slug>.html             : une sous-page par catégorie de volume >= THRESHOLD

Threshold pour créer une sous-page : 100 rows.
"""
import csv, html as _html, os, re
from pathlib import Path

SRC          = Path("/home/dahl/annuaire-scraper-pdf/out/pdf_findings.csv")
SCRAPER_ROOT = Path("/home/dahl/annuaire-scraper-pdf")
OUT_DIR      = Path("/home/dahl/justicelibre/web")
OUT_INDEX    = OUT_DIR / "inedits.html"
OUT_SUB      = OUT_DIR / "inedits"
OUT_SUB.mkdir(exist_ok=True)
CSV_COPY     = Path("/home/dahl/annuaire/web/pdf_findings.csv")

THRESHOLD = 100  # au-delà : sous-page dédiée
CSS_VER   = "20260715c"

CAT_LABELS = {
    "tgi":"Tribunal judiciaire","ti":"Tribunal de proximité","cour_appel":"Cour d'appel",
    "ta":"Tribunal administratif","caa":"Cour administrative d'appel","prudhommes":"Conseil de prud'hommes",
    "te":"Tribunal pour enfants","tribunal_commerce":"Tribunal de commerce","tae":"Tribunal des activités économiques",
    "cdad":"Conseil dép. d'accès au droit","mjd":"Maison de justice et du droit","spip":"SPIP",
    "ordre_avocats":"Ordre des avocats","vif_tj":"Pôle VIF (TJ)","vif_ca":"Pôle VIF (CA)","bav":"BAV",
    "dacs":"DACS","dgccrf":"DGCCRF","cabinet_ministeriel":"Cabinet ministériel",
    "administration_centrale":"Administration centrale","mairie":"Mairie","ccas":"CCAS",
    "police_municipale":"Police municipale","france_services":"France Services","epci":"Intercommunalité",
    "point_justice":"Point-justice","cij":"Centre d'info jeunesse","mission_locale":"Mission locale",
    "tresorerie":"Trésorerie","clic":"CLIC","pmi":"PMI","fr_renov":"France Rénov'","cio":"CIO",
    "pcb":"Point conseil budget","mda":"Maison des adolescents","pif":"Point info famille",
    "point_accueil_numerique":"Point accueil numérique","cci":"CCI","sous_pref":"Sous-préfecture",
    "prefecture":"Préfecture","conseil_dep":"Conseil départemental","conseil_reg":"Conseil régional",
    "ecole":"École / Établissement scolaire","autre":"Autre service public",
}

# Slug URL par catégorie (pour /inedits/<slug>.html)
CAT_SLUGS = {
    "ecole":                   "ecoles",
    "administration_centrale": "administrations-centrales",
    "prefecture":              "prefectures",
    "sous_pref":               "sous-prefectures",
    "cabinet_ministeriel":     "cabinets-ministeriels",
    "tresorerie":              "tresoreries",
    "dacs":                    "dacs",
    "dgccrf":                  "dgccrf",
    "autre":                   "autres",
}

CAT_ORDER = ["tgi","cour_appel","prudhommes","dacs","dgccrf","cabinet_ministeriel","administration_centrale","prefecture","sous_pref","tresorerie","ecole","autre"]

def esc(s): return _html.escape(str(s or ""), quote=True)

def fmt_date(s):
    if not s: return ""
    mois = ["","janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"]
    m = re.match(r"^(\d{4})-(\d{2})(?:-(\d{2}))?$", s)
    if not m: return s
    y, mo, d = m.group(1), int(m.group(2)), m.group(3)
    return f"{int(d)} {mois[mo]} {y}" if d else f"{mois[mo]} {y}"

# ─── Lecture CSV ─────────────────────────────────────────────────────
rows = []
with SRC.open(encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter=";"):
        sources_urls = [u.strip() for u in (r.get("source_url","")).split("|") if u.strip()]
        preuves = [p.strip() for p in (r.get("pdf_local","")).split("|")
                   if p.strip() and (SCRAPER_ROOT / p.strip()).exists()]
        rows.append({
            "mail":         r["mail"].strip().lower(),
            "organisme":    r["organisme"].strip(),
            "service":      r.get("service","").strip(),
            "category":     r.get("category","autre").strip() or "autre",
            "tel":          r.get("tel","").strip(),
            "site":         r.get("site_web","").strip(),
            "adresse":      r.get("adresse_postale","").strip(),
            "role":         r.get("role","").strip(),
            "source_url":   sources_urls[0] if sources_urls else "",
            "source_label": r.get("source_label","").strip(),
            "date_source":  r.get("date_source","").strip(),
            "date_fmt":     fmt_date(r.get("date_source","").strip()),
            "confidence":   r.get("confidence","").strip(),
            "preuve":       preuves[0] if preuves else "",
            "n_sources":    len(sources_urls),
        })

# Copie CSV pour le download
CSV_COPY.parent.mkdir(exist_ok=True)
CSV_COPY.write_bytes(SRC.read_bytes())

from collections import Counter
cat_counts = Counter(r["category"] for r in rows)

# ─── Rendu HTML row ──────────────────────────────────────────────────
def render_row(r):
    cat = CAT_LABELS.get(r["category"], r["category"])
    org_html = f'<strong>{esc(r["organisme"])}</strong>'
    if r["service"]: org_html += f'<div class="sub">{esc(r["service"])}</div>'
    if r["role"]:    org_html += f'<div class="role">{esc(r["role"])}</div>'

    contact_bits = []
    if r["tel"]:     contact_bits.append(f'<span class="tel">{esc(r["tel"])}</span>')
    if r["site"]:    contact_bits.append(f'<a href="{esc(r["site"] if r["site"].startswith("http") else "https://" + r["site"])}" target="_blank" rel="noopener">{esc(r["site"])}</a>')
    if r["adresse"]: contact_bits.append(f'<span class="adr">{esc(r["adresse"])}</span>')
    contact_html = "<br>".join(contact_bits) if contact_bits else '<span class="no-mail">-</span>'

    src_html = ""
    if r["source_url"]:
        m = re.match(r"https?://([^/]+)", r["source_url"])
        domain = m.group(1).replace("www.", "") if m else "PDF source"
        tooltip = r["source_label"] or "Voir le PDF source"
        src_html = f'<a href="{esc(r["source_url"])}" target="_blank" rel="noopener" title="{esc(tooltip)}">{esc(domain)} <span class="ext">↗</span></a>'
        if r["n_sources"] > 1:
            src_html += f' <span class="badge" title="Cette adresse a été trouvée dans {r["n_sources"]} PDFs différents">+{r["n_sources"]-1}</span>'
    if r["preuve"]:
        src_html += f' · <a href="/{esc(r["preuve"])}" target="_blank" rel="noopener" title="Copie locale archivée du PDF (au cas où le PDF officiel disparaîtrait)">archive <span class="ext">⤓</span></a>'

    date_html = esc(r["date_fmt"]) if r["date_fmt"] else '<span class="no-mail">-</span>'

    # Badge "service à vérifier" pour les rows low confidence
    org_extra = ""
    if r["confidence"] == "low":
        org_extra = ' <span class="badge badge-warn" title="Le mail a été extrait verbatim du PDF, mais le rattachement au service exact est incertain">service à vérifier</span>'

    data_attrs = f'data-cat="{esc(r["category"])}" data-search="{esc((r["organisme"] + " " + r["service"] + " " + r["mail"] + " " + r["role"] + " " + cat).lower())}"'
    return (f'<tr {data_attrs}>'
            f'<td class="type"><span class="badge">{esc(cat)}</span></td>'
            f'<td class="nom">{org_html}{org_extra}</td>'
            f'<td class="mail"><a href="mailto:{esc(r["mail"])}">{esc(r["mail"])}</a></td>'
            f'<td class="date">{date_html}</td>'
            f'<td class="contact">{contact_html}</td>'
            f'<td class="src">{src_html}</td>'
            f'</tr>')

# ─── Template partagé (index + sous-pages) ───────────────────────────
def page_template(*, title, meta_desc, h1_html, intro_html, subset_rows, extra_top_html="", show_nav_back=False, breadcrumb=""):
    """Génère une page complète avec table, filtres, FAB. subset_rows = liste
    de rows à afficher. Si subset_rows contient plusieurs catégories, le
    dropdown filtre est activé ; sinon il est masqué."""

    cats_in_subset = Counter(r["category"] for r in subset_rows)
    show_cat_filter = len(cats_in_subset) > 1

    # Dropdown items (uniquement les catégories présentes dans ce subset)
    cat_opts = [("", f"Toutes les catégories ({len(subset_rows)})")]
    for c in CAT_ORDER:
        if cats_in_subset.get(c):
            cat_opts.append((c, f"{CAT_LABELS.get(c, c)} ({cats_in_subset[c]})"))
    cat_panel_html = "".join(
        f'<div class="cs-item{" selected" if i==0 else ""}" data-value="{esc(k)}" data-label="{esc(v)}">{esc(v)}</div>'
        for i, (k, v) in enumerate(cat_opts)
    )

    # Fil d'ariane : inédits = enfant de l'annuaire. breadcrumb = label de la
    # sous-page (vide → page index inédits).
    IN = '<a href="/inedits.html">Adresses inédites</a>'
    if breadcrumb:
        crumb_tail = f'{IN} &nbsp;›&nbsp; {esc(breadcrumb)}'
        crumb_last_jsonld = esc(breadcrumb)
    else:
        crumb_tail = 'Adresses inédites'
        crumb_last_jsonld = 'Adresses inédites'
    breadcrumb_html = (
        '<div class="page-subbar">\n'
        f'  <div class="crumb"><a href="/">Accueil</a> &nbsp;›&nbsp; '
        f'<a href="/annuaire.html">Annuaire</a> &nbsp;›&nbsp; {crumb_tail}</div>\n'
        '</div>'
    )
    breadcrumb_jsonld = (
        '<script type="application/ld+json">{"@context": "https://schema.org", '
        '"@type": "BreadcrumbList", "itemListElement": ['
        '{"@type": "ListItem", "position": 1, "name": "Accueil", "item": "https://justicelibre.org/"}, '
        '{"@type": "ListItem", "position": 2, "name": "Annuaire", "item": "https://justicelibre.org/annuaire.html"}, '
        + ('{"@type": "ListItem", "position": 3, "name": "Adresses in\\u00e9dites", "item": "https://justicelibre.org/inedits.html"}, '
           f'{{"@type": "ListItem", "position": 4, "name": "{crumb_last_jsonld}"}}'
           if breadcrumb else
           '{"@type": "ListItem", "position": 3, "name": "Adresses in\\u00e9dites"}')
        + ']}</script>'
    )

    filters_html = ""
    if show_cat_filter:
        filters_html = f"""
    <div class="cs-wrap" id="fcatCs">
      <div class="cs-display" role="button" tabindex="0" aria-haspopup="listbox">
        <span class="cs-display-text">Toutes les catégories ({len(subset_rows)})</span>
        <span class="chev">▾</span>
      </div>
      <div class="cs-panel" role="listbox">{cat_panel_html}</div>
    </div>
    <input type="hidden" id="fcat" value="">"""

    table_body = "\n".join(render_row(r) for r in subset_rows)

    back_html = ""
    if show_nav_back:
        back_html = '<p style="margin-bottom:1rem"><a href="/inedits.html">← Retour à l\'index des inédits</a></p>'

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script>/* theme resolver — évite le flash, doit rester avant les CSS */
(function(){{try{{var s=localStorage.getItem("jl-theme");
if(s==="light"||s==="dark")document.documentElement.setAttribute("data-theme",s);}}catch(e){{}}}})();</script>
<title>{title} · justicelibre.org</title>
<meta name="description" content="{esc(meta_desc)}">
<link rel="icon" type="image/svg+xml" href="/logo.svg">
<meta property="og:title" content="{esc(title)} · justicelibre.org">
<meta property="og:description" content="{esc(meta_desc)}">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:ital,opsz,wght@0,9..40,300..800;1,9..40,300..800&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/styles/tokens.css?v=20260501">
<link rel="stylesheet" href="/styles/base.css?v=20260720">
<link rel="stylesheet" href="/styles/components.css?v=20260719b">
<link rel="stylesheet" href="/styles/annuaire.css?v={CSS_VER}">
{breadcrumb_jsonld}
<style>
.hero h1 em{{color:#7a1e2f}}
.wrap-wide{{max-width:1500px;margin:0 auto;padding:0 1rem}}
.tbl-full{{overflow-x:auto;background:var(--white);border:1px solid var(--line);border-radius:6px}}
.tbl-full table.data{{width:100%;border-collapse:collapse;table-layout:fixed}}
.tbl-full table.data td,.tbl-full table.data th{{overflow:hidden;padding:.7rem .85rem;vertical-align:top}}
.tbl-full table.data th{{text-overflow:ellipsis}}
.tbl-full table.data td.type .badge{{white-space:normal;line-height:1.25;display:inline-block}}
.tbl-full table.data th:nth-child(1),.tbl-full table.data td:nth-child(1){{width:14%}}
.tbl-full table.data th:nth-child(2),.tbl-full table.data td:nth-child(2){{width:24%}}
.tbl-full table.data th:nth-child(3),.tbl-full table.data td:nth-child(3){{width:19%;word-break:break-word}}
.tbl-full table.data th:nth-child(4),.tbl-full table.data td:nth-child(4){{width:13%}}
.tbl-full table.data th:nth-child(5),.tbl-full table.data td:nth-child(5){{width:11%}}
.tbl-full table.data th:nth-child(6),.tbl-full table.data td:nth-child(6){{width:19%}}
.tbl-full td.nom .sub{{font-size:.78rem;color:var(--muted);margin-top:.15rem;font-style:italic}}
.tbl-full td.nom .role{{font-size:.78rem;color:var(--body);margin-top:.2rem;line-height:1.35}}
.tbl-full td.contact{{font-size:.82rem;line-height:1.5}}
.tbl-full td.contact .tel{{color:var(--muted)}}
.tbl-full td.contact .adr{{color:var(--muted);font-style:italic}}
.tbl-full td.date{{white-space:nowrap;font-size:.85rem;color:var(--muted)}}
.tbl-full td.src{{font-size:.78rem;max-width:280px}}
.tbl-full td.src a{{color:var(--teal);text-decoration:none}}
.tbl-full td.src a:hover{{text-decoration:underline}}
.tbl-full td.src .ext{{font-size:.85em;opacity:.7;display:inline-block;transform:translateY(-1px)}}
.tbl-full td.src .badge{{background:var(--cream);color:var(--muted);font-size:.7rem;padding:.1rem .35rem}}
.badge-warn{{background:#fef9e8;color:#b8932b;font-size:.7rem;font-weight:500}}
th.sortable{{cursor:pointer;user-select:none}}
th.sortable:hover{{color:var(--teal)}}
th.sortable .arr{{opacity:.4;margin-left:.3rem;font-size:.7em}}
th.sortable.sorted .arr{{opacity:1}}
tr.hidden{{display:none}}
.inedits-stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1rem;margin:1.5rem 0}}
.inedits-stats .tile{{background:var(--white);border:1px solid var(--line);border-radius:4px;padding:1rem;text-align:center}}
.inedits-stats .tile .n{{font-family:var(--display);font-size:2rem;color:var(--teal);line-height:1}}
.inedits-stats .tile .lbl{{font-size:.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-top:.4rem}}
.cat-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:1rem;margin:1.5rem 0}}
.cat-grid a{{display:block;padding:1.2rem;background:var(--white);border:1px solid var(--line);border-radius:4px;text-decoration:none;color:var(--ink);transition:all .15s}}
.cat-grid a:hover{{border-color:var(--teal);transform:translateY(-1px);box-shadow:0 3px 10px rgba(0,0,0,.06)}}
.cat-grid .cat-n{{font-family:var(--display);font-size:1.4rem;color:#7a1e2f;line-height:1}}
.cat-grid .cat-l{{font-size:.85rem;margin-top:.4rem;color:var(--body)}}
.fab-signal{{position:fixed;bottom:1.5rem;right:1.5rem;z-index:900;width:3rem;height:3rem;border-radius:50%;background:var(--teal);color:#fff;border:none;font-size:1.4rem;font-family:'DM Serif Display',serif;font-weight:700;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.25);display:flex;align-items:center;justify-content:center;transition:all .15s}}
.fab-signal:hover{{background:var(--ink);transform:translateY(-2px);box-shadow:0 6px 18px rgba(0,0,0,.35)}}
.fab-signal::before{{content:"!";line-height:1}}
@media(max-width:640px){{.fab-signal{{bottom:1rem;right:1rem;width:2.6rem;height:2.6rem;font-size:1.2rem}}}}
</style>
<script defer src="/topbar.js?v=5"></script>
</head>
<body>

<div data-topbar-mount></div>
{breadcrumb_html}

<section class="hero">
  {h1_html}
  {intro_html}
</section>

<main class="wrap">
{extra_top_html}
{back_html}

<section class="block">
  <div class="download-row">
    <a href="/data/pdf_findings.csv" download>Télécharger CSV brut (toutes catégories, {len(rows)} rows)</a>
    <span class="kbd">Réutilisable, Licence Ouverte 2.0 (Etalab)</span>
  </div>

  <div class="filters">
    {filters_html}
    <input type="text" id="q" placeholder="Rechercher : organisme, service, mail, mot-clé…" autocomplete="off">
    <span class="count" id="count">{len(subset_rows)} / {len(subset_rows)} fiches</span>
  </div>

  <div class="wrap-wide">
  <div class="tbl-full">
    <table class="data">
      <thead>
        <tr>
          <th class="sortable" data-col="cat" title="Catégorie">Catégorie<span class="arr">▲▼</span></th>
          <th class="sortable" data-col="nom" title="Organisme / Service">Organisme / Service<span class="arr">▲▼</span></th>
          <th class="sortable" data-col="mail" title="Adresse électronique">Adresse électronique<span class="arr">▲▼</span></th>
          <th class="sortable" data-col="date" title="Dernière mention (date du PDF où l'adresse a été vue)">Dernière mention<span class="arr">▲▼</span></th>
          <th title="Téléphone, site web, adresse postale si disponibles">Contact</th>
          <th title="Lien vers le PDF officiel où l'adresse a été trouvée">Source PDF</th>
        </tr>
      </thead>
      <tbody id="tbody">
{table_body}
      </tbody>
    </table>
  </div>
  </div>
</section>

</main>

<footer class="foot">
  justicelibre.org · <a href="/">Accueil</a> · <a href="/annuaire.html">Annuaire principal</a> · <a href="/inedits.html">Inédits</a> · <a href="/search.html">Recherche</a> · <a href="https://github.com/Dahliyaal/justicelibre">GitHub</a> · Contenus sous Licence Ouverte 2.0 (Etalab).
</footer>

<button type="button" class="fab-signal" id="fabSignal" aria-label="Signaler ou informations légales" title="Signaler une adresse - Informations légales"></button>

<script>
(function(){{
  function bindCs(wrapId, hiddenId){{
    var wrap = document.getElementById(wrapId);
    if (!wrap) return;
    var display = wrap.querySelector('.cs-display');
    var dispText = wrap.querySelector('.cs-display-text');
    var panel = wrap.querySelector('.cs-panel');
    var hidden = document.getElementById(hiddenId);
    display.addEventListener('click', function(e){{
      e.stopPropagation();
      document.querySelectorAll('.cs-wrap.open').forEach(function(w){{ if (w !== wrap) w.classList.remove('open'); }});
      wrap.classList.toggle('open');
    }});
    panel.addEventListener('click', function(e){{
      var el = e.target.closest('[data-value]');
      if (!el) return;
      hidden.value = el.dataset.value;
      dispText.textContent = el.dataset.label;
      panel.querySelectorAll('.selected').forEach(function(n){{ n.classList.remove('selected'); }});
      el.classList.add('selected');
      wrap.classList.remove('open');
      hidden.dispatchEvent(new Event('change'));
    }});
  }}
  document.addEventListener('click', function(){{
    document.querySelectorAll('.cs-wrap.open').forEach(function(w){{ w.classList.remove('open'); }});
  }});
  document.addEventListener('keydown', function(e){{
    if (e.key === 'Escape') document.querySelectorAll('.cs-wrap.open').forEach(function(w){{ w.classList.remove('open'); }});
  }});
  bindCs('fcatCs', 'fcat');

  var rows = Array.prototype.slice.call(document.querySelectorAll('#tbody tr'));
  var TOTAL = rows.length;
  var count = document.getElementById('count');
  var q = document.getElementById('q');
  var fcat = document.getElementById('fcat');

  function apply(){{
    var qv = q.value.trim().toLowerCase();
    var cv = fcat ? fcat.value : '';
    var n = 0;
    for (var i=0; i<rows.length; i++) {{
      var r = rows[i];
      var okCat = !cv || r.dataset.cat === cv;
      var okQ = !qv || r.dataset.search.indexOf(qv) !== -1;
      if (okCat && okQ) {{ r.classList.remove('hidden'); n++; }}
      else r.classList.add('hidden');
    }}
    count.textContent = n.toLocaleString('fr-FR') + ' / ' + TOTAL.toLocaleString('fr-FR') + ' fiches';
  }}
  var timer;
  q.addEventListener('input', function(){{ clearTimeout(timer); timer = setTimeout(apply, 150); }});
  if (fcat) fcat.addEventListener('change', apply);

  var sortState = {{col: null, dir: 1}};
  function sortBy(col){{
    var dir = (sortState.col === col ? -sortState.dir : 1);
    sortState = {{col: col, dir: dir}};
    var tbody = document.getElementById('tbody');
    var arr = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    arr.sort(function(a, b){{
      var av, bv;
      if (col === 'cat')  {{ av = a.querySelector('td.type').textContent; bv = b.querySelector('td.type').textContent; }}
      else if (col === 'nom')  {{ av = a.querySelector('td.nom').textContent; bv = b.querySelector('td.nom').textContent; }}
      else if (col === 'mail') {{ av = a.querySelector('td.mail').textContent; bv = b.querySelector('td.mail').textContent; }}
      else if (col === 'date') {{ av = a.querySelector('td.date').textContent; bv = b.querySelector('td.date').textContent; }}
      av = av.toLowerCase(); bv = bv.toLowerCase();
      return av < bv ? -dir : av > bv ? dir : 0;
    }});
    for (var i=0; i<arr.length; i++) tbody.appendChild(arr[i]);
    document.querySelectorAll('th.sortable').forEach(function(th){{
      th.classList.toggle('sorted', th.dataset.col === col);
      var arrEl = th.querySelector('.arr');
      if (th.dataset.col === col) arrEl.textContent = dir > 0 ? '▲' : '▼';
      else arrEl.textContent = '▲▼';
    }});
  }}
  document.querySelectorAll('th.sortable').forEach(function(th){{
    th.addEventListener('click', function(){{ sortBy(th.dataset.col); }});
  }});

  var fab = document.getElementById('fabSignal');
  if (fab) fab.addEventListener('click', function(){{
    var to = 'contact' + String.fromCharCode(64) + 'justicelibre.org';
    var body = 'Adresse concernée :\\n\\nMotif du signalement (adresse morte, retrait demandé par l\\'agent, autre) :\\n';
    var ghHref = 'https://github.com/Dahliyaal/justicelibre/issues/new?title=' + encodeURIComponent('Signalement annuaire inedits') + '&body=' + encodeURIComponent(body);
    var overlay = document.createElement('div');
    overlay.className = 'jl-modal-overlay';
    overlay.innerHTML = '<div class="jl-modal" role="dialog" aria-modal="true" style="max-width:640px">'
      + '<button type="button" class="jl-modal-close" aria-label="Fermer">×</button>'
      + '<h3>Adresses nominatives et signalement</h3>'
      + '<p class="jl-modal-lead"><strong>Pourquoi certaines adresses contiennent un nom (prenom.nom@admin.fr) ?</strong></p>'
      + '<p class="jl-modal-lead">Ces adresses sont publiées ici parce que l\\'administration les a elle-même publiées dans un PDF officiel (voir colonne <em>Source PDF</em>). Elles constituent des données professionnelles d\\'agents publics, communicables au titre de l\\'article <strong>L. 311-6 du CRPA</strong> (position constante de la CADA : avis 2007-3348, 2010-2445, 2019-4471).</p>'
      + '<p class="jl-modal-lead"><strong>Droit d\\'opposition (RGPD article 21).</strong> Tout agent peut demander le retrait de son adresse. Le retrait est traité dans les meilleurs délais.</p>'
      + '<p class="jl-modal-lead"><strong>Pour signaler une adresse (retrait, adresse morte, correction) :</strong></p>'
      + '<div class="jl-modal-actions">'
      +   '<a class="jl-modal-btn primary" href="' + ghHref + '" target="_blank" rel="noopener">Ouvrir un ticket GitHub</a>'
      + '</div>'
      + '<p class="jl-modal-hint">ou par email : <code>contact' + String.fromCharCode(64) + 'justicelibre.org</code></p>'
      + '</div>';
    document.body.appendChild(overlay);
    document.body.style.overflow = 'hidden';
    function close(){{ overlay.remove(); document.body.style.overflow = ''; document.removeEventListener('keydown', onEsc); }}
    function onEsc(ev){{ if (ev.key === 'Escape') close(); }}
    overlay.addEventListener('click', function(ev){{ if (ev.target === overlay || ev.target.classList.contains('jl-modal-close')) close(); }});
    document.addEventListener('keydown', onEsc);
  }});

  var themeBtn = document.getElementById('themeToggle');
  if (themeBtn) themeBtn.addEventListener('click', function(){{
    var html = document.documentElement;
    var isDark = html.getAttribute('data-theme') === 'dark' || (!html.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
    var next = isDark ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    try {{ localStorage.setItem('jl-theme', next); }} catch(e){{}}
  }});
}})();
</script>
</body>
</html>
"""

# ─── Split : grosses catégories → sous-page ; petites → dans l'index ─
big_cats = [c for c in CAT_ORDER if cat_counts.get(c, 0) >= THRESHOLD]
small_cats = [c for c in CAT_ORDER if 0 < cat_counts.get(c, 0) < THRESHOLD]
index_rows = [r for r in rows if r["category"] in small_cats]
index_rows.sort(key=lambda r: (CAT_ORDER.index(r["category"]) if r["category"] in CAT_ORDER else 99, r["organisme"].lower()))

# ─── Génération sous-pages ───────────────────────────────────────────
for cat in big_cats:
    slug = CAT_SLUGS.get(cat, cat.replace("_","-"))
    sub_rows = [r for r in rows if r["category"] == cat]
    sub_rows.sort(key=lambda r: r["organisme"].lower())
    label = CAT_LABELS.get(cat, cat)

    h1 = f'<h1><em>{esc(label)}</em> - Adresses inédites</h1>'
    intro = f"""<p>{len(sub_rows)} adresses email de la catégorie <strong>{esc(label)}</strong>, scrapées depuis des PDF gouvernementaux et <strong>vérifiées absentes</strong> du dump DILA et de l'API <code>api-lannuaire.service-public.fr</code>. Chaque adresse est vérifiable via le PDF source.</p>
    <p class="sources">Source : scraping automatisé de PDF gouvernementaux. Mise à jour : 16 juillet 2026.</p>"""
    meta_desc = f"{len(sub_rows)} adresses email {esc(label).lower()} scrapées depuis PDF gouvernementaux, absentes des annuaires officiels."

    html = page_template(
        title=f"{label} inédites",
        meta_desc=meta_desc,
        h1_html=h1,
        intro_html=intro,
        subset_rows=sub_rows,
        show_nav_back=True,
        breadcrumb=label,
    )
    out_path = OUT_SUB / f"{slug}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"  /inedits/{slug}.html : {len(sub_rows)} rows ({len(html)//1024} KB)")

# ─── Génération index ────────────────────────────────────────────────
n_organismes = len({r["organisme"] for r in rows})
n_avec_tel   = sum(1 for r in rows if r["tel"])
n_avec_dates = sum(1 for r in rows if r["date_source"])

# Cards vers les sous-pages
cards_html = ""
for cat in big_cats:
    slug = CAT_SLUGS.get(cat, cat.replace("_","-"))
    n = cat_counts[cat]
    cards_html += f'<a href="/inedits/{slug}.html"><div class="cat-n">{n:,}</div><div class="cat-l">{esc(CAT_LABELS.get(cat, cat))}</div></a>\n'

extra_top = f"""
<section class="block">
  <div class="inedits-stats">
    <div class="tile"><div class="n">{len(rows):,}</div><div class="lbl">Adresses uniques</div></div>
    <div class="tile"><div class="n">{n_organismes:,}</div><div class="lbl">Organismes distincts</div></div>
    <div class="tile"><div class="n">{n_avec_tel:,}</div><div class="lbl">avec téléphone</div></div>
    <div class="tile"><div class="n">{n_avec_dates:,}</div><div class="lbl">datées</div></div>
  </div>

  <div class="infobox">
    <p><strong>Pourquoi ces adresses n'apparaissent pas ailleurs ?</strong> L'annuaire officiel <code>api-lannuaire.service-public.fr</code> ne publie que les entités <em>chapeau</em> (ministères, directions générales). Les bureaux internes, cellules spécialisées, cabinets ministériels, écoles et rectorats utilisent souvent des adresses fonctionnelles qui n'y figurent pas, mais qui apparaissent au fil des circulaires, rapports et présentations publiés en PDF sur les sites gouvernementaux. Cette page les rassemble.</p>
    <p><strong>Fiabilité.</strong> Chaque adresse pointe vers le PDF où elle a été trouvée. La date affichée est celle du document, ce qui donne une indication sur la fraîcheur.</p>
    <p><strong>Badge « service à vérifier ».</strong> Certaines adresses (badge jaune) ont été extraites verbatim d'un PDF, mais le rattachement exact au bureau ou service émetteur reste incertain. L'adresse elle-même est fiable, seul le contexte l'est moins.</p>
  </div>
</section>

<section class="block">
  <h2>Sous-pages par catégorie</h2>
  <p class="intro">Les catégories volumineuses ont leur propre page dédiée. Les petites catégories ({len(index_rows)} fiches au total) sont listées directement ci-dessous.</p>
  <div class="cat-grid">
{cards_html}
  </div>
</section>
""" + (f'<section class="block"><h2>Petites catégories ({len(index_rows)} fiches)</h2></section>' if index_rows else '')

# Index HTML
h1_index = '<h1>Adresses <em>inédites</em> - PDF gouvernementaux.</h1>'
intro_index = f"""<p>{len(rows):,} adresses email officielles d'administrations françaises, extraites de PDF publiés sur des sites <code>.gouv.fr</code>, <strong>vérifiées absentes</strong> du dump quotidien DILA et de l'API <code>api-lannuaire.service-public.fr</code>. Chaque adresse est accompagnée du PDF source cliquable et de sa date de rédaction.</p>
<p class="sources">Source : scraping automatisé de PDF gouvernementaux. Mise à jour : 16 juillet 2026.</p>"""

if index_rows:
    index_html = page_template(
        title="Adresses inédites - PDF gouvernementaux",
        meta_desc=f"{len(rows)} adresses email officielles scrapées depuis PDF gouvernementaux, absentes des annuaires publics. Écoles, cabinets ministériels, administrations centrales, préfectures.",
        h1_html=h1_index,
        intro_html=intro_index,
        subset_rows=index_rows,
        extra_top_html=extra_top,
    )
else:
    # Pas de petite catégorie : index sans table, juste les cards
    index_html = page_template(
        title="Adresses inédites - PDF gouvernementaux",
        meta_desc=f"{len(rows)} adresses email officielles scrapées depuis PDF gouvernementaux, absentes des annuaires publics.",
        h1_html=h1_index,
        intro_html=intro_index,
        subset_rows=[],
        extra_top_html=extra_top,
    )

OUT_INDEX.write_text(index_html, encoding="utf-8")
print(f"\n[inedits] index /inedits.html : {len(index_rows)} rows inline · {len(big_cats)} sous-pages · {len(index_html)//1024} KB")
print(f"[inedits] total : {len(rows)} adresses sur {len(big_cats) + (1 if index_rows else 0)} pages")
print(f"[inedits] breakdown : {dict(cat_counts)}")

# ─── Patch annuaire.html : MAJ automatique du compte dans le bouton CTA ─
# Patche à la fois le template et la sortie du build annuaire (deux fichiers).
pretty = f"{len(rows):,}".replace(",", " ")  # 3 941 style FR (espace fine)
for p in [OUT_DIR / "annuaire.html", Path("/home/dahl/annuaire/web/annuaire.html")]:
    if not p.exists(): continue
    src = p.read_text(encoding="utf-8")
    patched = re.sub(
        r"(<!-- INEDITS_COUNT_START -->).*?(<!-- INEDITS_COUNT_END -->)",
        rf"\g<1>{pretty}\g<2>",
        src,
    )
    if patched != src:
        p.write_text(patched, encoding="utf-8")
        print(f"[inedits] {p} patché : compteur mis à {pretty}")
