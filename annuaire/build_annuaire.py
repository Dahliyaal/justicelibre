#!/usr/bin/env python3
"""Convertit les CSVs annuaire en JSON compact + génère l'index HTML
statique + une sous-page HTML statique par catégorie API volumineuse.

Sortie dans /home/dahl/annuaire/web/ :
- annuaire_juridictions.json  (juri + manuels + API tous)
- annuaire_prada.json         (PRADA CADA)
- annuaire_meta.json          (dates, counts, coverage)
- annuaire_juridictions.csv   (copie brute pour download)
- annuaire_prada.csv          (idem)
- annuaire.html               (index : juri + admin centrales + PRADA
                               + grille de liens vers les sous-pages)
- annuaire/<slug>.html        (une page statique par catégorie API >= 100)

Rationale : l'index chargeait 71 k fiches en HTML brut (28 MB), ce qui
freeze les navigateurs. Le refactor le limite à ~5 k rows cœur de site.
Les 65 k autres fiches sont réparties sur des sous-pages statiques (SEO
conservé) avec pagination JS locale (500 rows visibles par défaut).
"""
import csv, html as _html, json, os, re, shutil
from datetime import datetime, timezone
from pathlib import Path

SRC = Path(os.environ.get("ANNUAIRE_SRC", "/home/dahl/annuaire"))
OUT = SRC / "web"
OUT.mkdir(exist_ok=True)
OUT_SUB = OUT / "annuaire"
OUT_SUB.mkdir(exist_ok=True)
REPO_TEMPLATE = Path(os.environ.get("ANNUAIRE_REPO", "/home/dahl/justicelibre")) / "web/annuaire.html"
REPO_SITEMAP = Path(os.environ.get("ANNUAIRE_REPO", "/home/dahl/justicelibre")) / "web/sitemap.xml"

TYPE_LABELS = {
    # Juridictions (dump DILA)
    "tgi":               "Tribunal judiciaire",
    "ti":                "Tribunal de proximité",
    "cour_appel":        "Cour d'appel",
    "ta":                "Tribunal administratif",
    "caa":               "Cour administrative d'appel",
    "prudhommes":        "Conseil de prud'hommes",
    "te":                "Tribunal pour enfants",
    "tribunal_commerce": "Tribunal de commerce",
    "tae":               "Tribunal des activités économiques",
    "cdad":              "Conseil dép. d'accès au droit",
    "mjd":               "Maison de justice et du droit",
    "spip":              "SPIP (insertion & probation)",
    "ordre_avocats":     "Ordre des avocats",
    "vif_tj":            "Pôle violences intra-familiales (TJ)",
    "vif_ca":            "Pôle violences intra-familiales (CA)",
    "bav":               "Bureau d'aide aux victimes",
    # Ajouts manuels
    "dacs":              "DACS (ministère de la Justice)",
    "dgccrf":            "DGCCRF (répression des fraudes)",
    "cabinet_ministeriel": "Cabinet ministériel",
    # Depuis l'API (pivot_kind)
    "administration_centrale": "Administration centrale",
    "mairie":            "Mairie",
    "ccas":              "CCAS (centre d'action sociale)",
    "police_municipale": "Police municipale",
    "france_services":   "France Services",
    "epci":              "Intercommunalité (EPCI)",
    "point_justice":     "Point-justice",
    "cij":               "Centre d'info jeunesse",
    "mission_locale":    "Mission locale",
    "tresorerie":        "Trésorerie",
    "clic":              "CLIC (personnes âgées)",
    "pmi":               "PMI (mère & enfant)",
    "fr_renov":          "France Rénov'",
    "cio":               "CIO (orientation scolaire)",
    "pcb":               "Point conseil budget",
    "mda":               "Maison des adolescents",
    "pif":               "Point info famille",
    "point_accueil_numerique": "Point accueil numérique",
    "cci":               "CCI (chambre de commerce)",
    "sous_pref":         "Sous-préfecture",
    "prefecture":        "Préfecture",
    "conseil_dep":       "Conseil départemental",
    "conseil_reg":       "Conseil régional",
    "autre":             "Autre service public",
}

PIVOT_TO_CAT = {
    "chapeau": "administration_centrale",
}
INCLUDE_NAMES = True  # publier les noms PRADA (art. L.330-1 CRPA impose de désigner cette personne)

# Catégories cœur de site injectées dans l'HTML statique de l'index.
STATIC_CATS = {
    "tgi","ti","cour_appel","ta","caa","tribunal_commerce","tae","prudhommes","te","spip",
    "cdad","mjd","ordre_avocats","vif_tj","vif_ca","bav",
    "dacs","dgccrf","cabinet_ministeriel","administration_centrale",
}

# Sous-pages : slug URL → (type interne, label affichable, description SEO).
# Une entrée par catégorie API de volume >= 100 (les autres tombent dans autres.html).
SUBPAGES = [
    ("mairies",           "mairie",                  "Mairies",
     "Adresses email officielles des mairies françaises. Source : API annuaire.service-public.fr."),
    ("ccas",              "ccas",                    "CCAS (centres communaux d'action sociale)",
     "Adresses email des CCAS et CIAS communaux. Source : API annuaire.service-public.fr."),
    ("police-municipale", "police_municipale",       "Polices municipales",
     "Adresses email des polices municipales françaises. Source : API annuaire.service-public.fr."),
    ("france-services",   "france_services",         "Espaces France Services",
     "Adresses email des espaces France Services. Source : API annuaire.service-public.fr."),
    ("intercommunalites", "epci",                    "Intercommunalités (EPCI)",
     "Adresses email des communautés de communes, d'agglomération, urbaines et métropoles. Source : API annuaire.service-public.fr."),
    ("tresoreries",       "tresorerie",              "Trésoreries",
     "Adresses email des trésoreries de la DGFIP. Source : API annuaire.service-public.fr."),
    ("missions-locales",  "mission_locale",          "Missions locales",
     "Adresses email des missions locales pour l'insertion des jeunes. Source : API annuaire.service-public.fr."),
    ("cij",               "cij",                     "Centres d'information jeunesse (CIJ)",
     "Adresses email des CIJ et BIJ. Source : API annuaire.service-public.fr."),
    ("clic",              "clic",                    "CLIC (centres locaux d'information et de coordination)",
     "Adresses email des CLIC (personnes âgées). Source : API annuaire.service-public.fr."),
    ("pmi",               "pmi",                     "Centres PMI (protection maternelle et infantile)",
     "Adresses email des centres PMI. Source : API annuaire.service-public.fr."),
    ("cio",               "cio",                     "CIO (centres d'information et d'orientation)",
     "Adresses email des CIO scolaires. Source : API annuaire.service-public.fr."),
    ("france-renov",      "fr_renov",                "Espaces conseil France Rénov'",
     "Adresses email des espaces conseil France Rénov' (rénovation énergétique). Source : API annuaire.service-public.fr."),
    ("pcb",               "pcb",                     "Points conseil budget (PCB)",
     "Adresses email des points conseil budget. Source : API annuaire.service-public.fr."),
    ("mda",               "mda",                     "Maisons des adolescents",
     "Adresses email des maisons des adolescents. Source : API annuaire.service-public.fr."),
    ("pif",               "pif",                     "Points info famille",
     "Adresses email des points info famille. Source : API annuaire.service-public.fr."),
    ("accueil-numerique", "point_accueil_numerique", "Points d'accueil numérique",
     "Adresses email des points d'accueil numérique (démarches en ligne). Source : API annuaire.service-public.fr."),
    ("cci",               "cci",                     "Chambres de commerce et d'industrie (CCI)",
     "Adresses email des chambres de commerce et d'industrie. Source : API annuaire.service-public.fr."),
    ("sous-prefectures",  "sous_pref",               "Sous-préfectures",
     "Adresses email des sous-préfectures françaises. Source : API annuaire.service-public.fr."),
    ("point-justice",     "point_justice",           "Points-justice",
     "Adresses email des points-justice (accès au droit gratuit). Source : API annuaire.service-public.fr."),
]
SUBPAGE_TYPES = {t for (_, t, _, _) in SUBPAGES}

# ─── 1. juridictions locales (dump DILA) ────────────────────────────
juri_rows = []
stats = {}
with (SRC / "justice_mails.csv").open(encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter=";"):
        t = r["type"]
        has_mail = bool(r["mails"].strip())
        stats.setdefault(t, {"total": 0, "with_mail": 0})
        stats[t]["total"] += 1
        if has_mail:
            stats[t]["with_mail"] += 1
        juri_rows.append({
            "id":   r["id"],
            "type": t,
            "nom":  r["nom"],
            "mails": [m.strip() for m in r["mails"].split(";") if m.strip()] if r["mails"] else [],
            "tel":  r["tel"] or "",
            "site": r["site"] or "",
            "source": "dila",
        })

# ─── 2. ajouts manuels ──────────────────────────────────────────────
manual_rows = []
manual_path = SRC / "manual_additions.csv"
if manual_path.exists():
    with manual_path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if not r.get("mail"):
                continue
            cat = r.get("category") or "administration_centrale"
            manual_rows.append({
                "id":   f"manual:{r.get('organisme','?')[:60]}",
                "type": cat,
                "nom":  r["organisme"],
                "mails": [r["mail"].strip()],
                "tel":  "",
                "site": "",
                "source": "manuel",
                "source_url": r.get("source_url", "").strip(),
                "source_label": r.get("source_label", "").strip(),
                "contact_extra": r.get("contact", "").strip(),
            })

# ─── 2bis. API annuaire.service-public.fr ───────────────────────────
api_rows = []
api_path = SRC / "api_annuaire.csv"
if api_path.exists():
    with api_path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            mails = [m.strip() for m in r.get("mails", "").split(";") if m.strip()]
            if not mails:
                continue
            pk = r.get("pivot_kind", "chapeau") or "chapeau"
            cat = PIVOT_TO_CAT.get(pk, pk if pk in TYPE_LABELS else "autre")
            api_rows.append({
                "id": r.get("id", ""),
                "type": cat,
                "raw_pivot": pk,
                "nom": (r["nom"] + (f" ({r['sigle']})" if r.get("sigle") else "")),
                "mails": mails,
                "tel": r.get("telephone", ""),
                "site": r.get("site_internet", "").split(" ; ")[0] if r.get("site_internet") else "",
                "source": "api",
                "hierarchie": r.get("hierarchie", ""),
                "adresse_postale": r.get("adresse", ""),
            })

TYPE_ORDER = [
    "tgi","ti","cour_appel","ta","caa","tribunal_commerce","tae","prudhommes","te","spip",
    "cdad","mjd","ordre_avocats","vif_tj","vif_ca","bav","point_justice",
    "dacs","dgccrf","cabinet_ministeriel","administration_centrale",
    "prefecture","sous_pref","conseil_reg","conseil_dep","epci",
    "mairie","ccas","police_municipale",
    "france_services","tresorerie","cci","mission_locale","cij","cio",
    "clic","pmi","mda","pif","pcb","fr_renov","point_accueil_numerique",
    "autre",
]
type_rank = {t: i for i, t in enumerate(TYPE_ORDER)}

# Dédup DILA/API : les deux sources listent souvent la même juridiction
# (ex : BAV du TJ de Valenciennes présent dans le dump DILA sans mail ET
# dans l'API avec mail). On garde une seule fiche par (type, nom
# normalisé), en privilégiant celle qui a un mail. Sinon on gonfle
# artificiellement les compteurs (217 BAV affichés au lieu de 167).
def _norm(s):
    return " ".join((s or "").lower().split())

_dedup = {}
_dupes = 0
for r in juri_rows + manual_rows + api_rows:
    key = (r["type"], _norm(r["nom"]))
    prev = _dedup.get(key)
    if prev is None:
        _dedup[key] = r
    else:
        _dupes += 1
        # Garde celle qui a un mail. Si les deux ont un mail, garde la
        # plus riche (celle avec le plus de champs remplis).
        prev_has = bool(prev.get("mails"))
        curr_has = bool(r.get("mails"))
        if curr_has and not prev_has:
            _dedup[key] = r
        elif curr_has and prev_has:
            score = lambda x: sum(1 for k in ("tel","site","adresse_postale","hierarchie","source_url") if x.get(k))
            if score(r) > score(prev):
                _dedup[key] = r
print(f"[annuaire] dédup DILA/API : {_dupes} doublons retirés (sur {len(juri_rows)+len(manual_rows)+len(api_rows)} rows bruts)")

all_juri = sorted(_dedup.values(), key=lambda r: (type_rank.get(r["type"], 99), r["nom"]))

(OUT / "annuaire_juridictions.json").write_text(
    json.dumps({"type_labels": TYPE_LABELS, "rows": all_juri}, ensure_ascii=False, separators=(",", ":")),
    encoding="utf-8",
)

# ─── 3. PRADA ───────────────────────────────────────────────────────
prada_rows = []
prada_with_mail = 0
with (SRC / "prada_full.csv").open(encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter=";"):
        row = {"organisme": r["organisme"], "courriel": r["courriel"] or "", "adresse": r["adresse"] or ""}
        if INCLUDE_NAMES:
            row["prada"] = r["prada"] or ""
        if r["courriel"].strip():
            prada_with_mail += 1
        prada_rows.append(row)
prada_rows.sort(key=lambda r: r["organisme"].lower())
(OUT / "annuaire_prada.json").write_text(
    json.dumps({"rows": prada_rows, "includes_names": INCLUDE_NAMES}, ensure_ascii=False, separators=(",", ":")),
    encoding="utf-8",
)

# ─── 4. meta ────────────────────────────────────────────────────────
def mtime_iso(p): return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d") if p.exists() else None
API_DATE = mtime_iso(SRC / "api_annuaire.csv")
DILA_DATE = mtime_iso(SRC / "dila_annuaire_local.json")
CADA_DATE = mtime_iso(SRC / "prada_full.csv")

meta = {
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "sources": {
        "dila_dump": {"url": "https://lecomarquage.service-public.gouv.fr/donnees_locales_v4/all_latest.tar.bz2",
                      "downloaded": DILA_DATE,
                      "provider": "DILA (Premier ministre)"},
        "api_annuaire": {"url": "https://api-lannuaire.service-public.fr/",
                         "downloaded": API_DATE,
                         "provider": "DILA / annuaire.service-public.fr"},
        "cada_prada": {"url": "https://www.cada.fr/particulier/personnes-responsables-resultatss",
                       "downloaded": CADA_DATE,
                       "provider": "CADA"},
        "manual": {"downloaded": mtime_iso(manual_path), "count": len(manual_rows),
                   "note": "Adresses trouvées hors annuaires officiels, ajoutées manuellement avec source."},
    },
    "counts": {
        "juridictions_total":     len(juri_rows),
        "juridictions_with_mail": sum(1 for r in juri_rows if r["mails"]),
        "api_centraux_total":     sum(1 for r in api_rows if r["type"] == "administration_centrale"),
        "api_centraux_with_mail": sum(1 for r in api_rows if r["type"] == "administration_centrale" and r["mails"]),
        "api_total":              len(api_rows),
        "manual_additions":       len(manual_rows),
        "prada_total":            len(prada_rows),
        "prada_with_mail":        prada_with_mail,
        "grand_total":            len(juri_rows) + len(api_rows) + len(manual_rows) + len(prada_rows),
    },
    "coverage_by_type": {
        t: {"label": TYPE_LABELS.get(t, t), "total": s["total"], "with_mail": s["with_mail"],
            "rate": round(s["with_mail"] / s["total"] * 100, 1)}
        for t, s in stats.items()
    },
}
(OUT / "annuaire_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

# ─── 5. CSVs bruts pour download ────────────────────────────────────
shutil.copy(SRC / "justice_mails.csv", OUT / "annuaire_juridictions.csv")
shutil.copy(SRC / "prada_full.csv",    OUT / "annuaire_prada.csv")

# ─── 6. Rendu HTML des rows ─────────────────────────────────────────
def esc(s):
    return _html.escape(str(s), quote=True) if s else ""

SOURCE_BADGES = {
    "manuel": ('#fef9e8', '#b8932b', 'manuel', 'Source non officielle, documentée'),
    "api":    ('#e6f0f5', '#1e5568', 'api',    'Source : api-lannuaire.service-public.fr'),
}

def _source_badge(r):
    b = SOURCE_BADGES.get(r.get("source", ""))
    if not b:
        return ""
    bg, fg, txt, tip = b
    return f' <span class="badge" style="background:{bg};color:{fg}" title="{tip}">{txt}</span>'

def _mails_html(mails):
    if not mails:
        return '<span class="no-mail">non publié</span>'
    return "<br>".join(f'<a href="mailto:{esc(m)}">{esc(m)}</a>' for m in mails)

def _contact_html(r):
    parts = []
    if r.get("tel"):
        parts.append(f'<span class="tel">{esc(r["tel"])}</span>')
    if r.get("site"):
        parts.append(f'<a href="{esc(r["site"])}" target="_blank" rel="noopener">site</a>')
    if r.get("hierarchie"):
        parts.append(f'<span style="font-size:.72rem;color:var(--muted)">{esc(r["hierarchie"])}</span>')
    if r.get("adresse_postale"):
        parts.append(esc(r["adresse_postale"]).replace(" | ", "<br>"))
    if r.get("contact_extra"):
        parts.append(esc(r["contact_extra"]))
    if r.get("source_url"):
        parts.append(f'<a href="{esc(r["source_url"])}" target="_blank" rel="noopener" style="font-size:.72rem;color:#b8932b">source : {esc(r.get("source_label") or "document")}</a>')
    return "<br>".join(parts)

def _signal_button(r):
    if not r["mails"]:
        return ""
    data = json.dumps({"n": r["nom"], "c": TYPE_LABELS.get(r["type"], r["type"]), "m": r["mails"]}, ensure_ascii=False)
    from urllib.parse import quote as _q
    return f'<button type="button" class="signal" data-fiche="{_q(data)}">Signaler</button>'

def render_juri_row_index(r):
    """Row pour l'index : contact/action laissés vides, le JS les remplira au chargement."""
    cat = TYPE_LABELS.get(r["type"], r["type"])
    return (f'<tr><td class="type"><span class="badge">{esc(cat)}</span>{_source_badge(r)}</td>'
            f'<td class="nom">{esc(r["nom"])}</td>'
            f'<td class="mail">{_mails_html(r["mails"])}</td>'
            f'<td class="contact"></td><td class="action"></td></tr>')

def render_prada_row_index(r):
    mail_html = f'<a href="mailto:{esc(r["courriel"])}">{esc(r["courriel"])}</a>' if r["courriel"] else '<span class="no-mail">non publié</span>'
    sub = f'<div class="sub">{esc(r.get("prada",""))}</div>' if r.get("prada") else ""
    return (f'<tr><td class="type"><span class="badge prada">PRADA</span></td>'
            f'<td class="nom">{esc(r["organisme"])}{sub}</td>'
            f'<td class="mail">{mail_html}</td>'
            f'<td class="contact"></td><td class="action"></td></tr>')

def _signal_button_compact(r):
    """Version compacte : seul le nom est stocké en data-attr, les mails
    sont récupérés au clic depuis la cellule voisine de la même row."""
    if not r["mails"]:
        return ""
    return f'<button type="button" class="signal" data-n="{esc(r["nom"])}">Signaler</button>'

def render_sub_row(r, idx, paged_threshold, cat_label=None):
    """Row pour les sous-pages : contact + bouton signal statiques.
    Si cat_label est fourni (sous-pages mono-catégorie), on économise le
    lookup par row ; sinon (autres.html), on utilise le type de la row."""
    cls = ' class="jl-paged"' if idx >= paged_threshold else ""
    label = cat_label if cat_label is not None else esc(TYPE_LABELS.get(r["type"], r["type"]))
    return (f'<tr{cls}><td class="type"><span class="badge">{label}</span></td>'
            f'<td class="nom">{esc(r["nom"])}</td>'
            f'<td class="mail">{_mails_html(r["mails"])}</td>'
            f'<td class="contact">{_contact_html(r)}</td>'
            f'<td class="action">{_signal_button_compact(r)}</td></tr>')

# ─── 7. Split des rows API par catégorie ────────────────────────────
by_type = {}
for r in api_rows:
    by_type.setdefault(r["type"], []).append(r)

# La sous-page "autres" ramasse toute catégorie API pas dans STATIC_CATS
# ni dans les SUBPAGES nommées.
subpage_covered_types = STATIC_CATS | SUBPAGE_TYPES
autres_rows = []
for t, rows in by_type.items():
    if t not in subpage_covered_types:
        autres_rows.extend(rows)
autres_rows.sort(key=lambda r: (r["type"], r["nom"].lower()))

# ─── 8. Génération de l'index annuaire.html ─────────────────────────
# Sur l'index, on ne garde que : (a) tout ce qui n'est PAS de l'API
# (juri DILA + ajouts manuels), (b) les admin centrales de l'API. Les
# doublons API sur tgi/ti/cour_appel/etc. seraient redondants avec DILA
# et gonfleraient inutilement le HTML.
static_juri = [
    r for r in all_juri
    if r["type"] in STATIC_CATS
    and (r.get("source") != "api" or r["type"] == "administration_centrale")
]
static_rows = "\n".join(
    [render_juri_row_index(r) for r in static_juri]
    + [render_prada_row_index(r) for r in prada_rows]
)

# Grille de cards vers les sous-pages
def _fmt_n(n): return f"{n:,}".replace(",", " ")
cards = []
for slug, typ, label, _ in SUBPAGES:
    n = len(by_type.get(typ, []))
    if n == 0:
        continue
    cards.append(
        f'<a class="cat-card" href="/annuaire/{slug}.html">'
        f'<span class="cat-label">{esc(label)}</span>'
        f'<span class="cat-count"><strong>{_fmt_n(n)}</strong> fiches avec mail</span>'
        f'</a>'
    )
if autres_rows:
    cards.append(
        f'<a class="cat-card" href="/annuaire/autres.html">'
        f'<span class="cat-label">Autres services publics</span>'
        f'<span class="cat-count"><strong>{_fmt_n(len(autres_rows))}</strong> fiches (divers)</span>'
        f'</a>'
    )
cards_html = "\n".join(cards)

template = REPO_TEMPLATE.read_text(encoding="utf-8")
pattern_rows = re.compile(r"(<!-- STATIC_ROWS_START.*?-->).*?(<!-- STATIC_ROWS_END -->)", re.DOTALL)
pattern_cards = re.compile(r"(<!-- CATEGORY_CARDS_START.*?-->).*?(<!-- CATEGORY_CARDS_END -->)", re.DOTALL)
if not pattern_rows.search(template):
    raise RuntimeError("placeholder STATIC_ROWS_START/END introuvable dans le template")
if not pattern_cards.search(template):
    raise RuntimeError("placeholder CATEGORY_CARDS_START/END introuvable dans le template")
final = pattern_rows.sub(lambda m: f"{m.group(1)}\n{static_rows}\n{m.group(2)}", template)
final = pattern_cards.sub(lambda m: f"{m.group(1)}\n{cards_html}\n{m.group(2)}", final)
(OUT / "annuaire.html").write_text(final, encoding="utf-8")

# ─── 9. Génération des sous-pages ───────────────────────────────────
PAGE_STEP = 500

SUB_TEMPLATE_HEAD = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script>(function(){try{var s=localStorage.getItem('jl-theme');
if(s==='light'||s==='dark')document.documentElement.setAttribute('data-theme',s);}catch(e){}})();</script>
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="icon" type="image/svg+xml" href="/logo.svg">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
<meta property="og:url" content="https://justicelibre.org/annuaire/{slug}.html">
<link rel="canonical" href="https://justicelibre.org/annuaire/{slug}.html">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:ital,opsz,wght@0,9..40,300..800;1,9..40,300..800&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/styles/tokens.css?v=20260501">
<link rel="stylesheet" href="/styles/base.css?v=20260720">
<link rel="stylesheet" href="/styles/components.css?v=20260719b">
<link rel="stylesheet" href="/styles/annuaire.css?v=20260715c">
<script defer src="/topbar.js?v=5"></script>
<script type="application/ld+json">{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "Accueil", "item": "https://justicelibre.org/"}, {"@type": "ListItem", "position": 2, "name": "Annuaire", "item": "https://justicelibre.org/annuaire.html"}, {"@type": "ListItem", "position": 3, "name": "{h1}"}]}</script>
</head>
<body>
<div data-topbar-mount></div>
<div class="page-subbar">
  <div class="crumb"><a href="/">Accueil</a> &nbsp;›&nbsp; <a href="/annuaire.html">Annuaire</a> &nbsp;›&nbsp; {h1}</div>
</div>

<section class="hero">
  <div class="back-link"><a href="/annuaire.html">Retour à l'annuaire général</a></div>
  <h1>{h1}</h1>
  <p><strong>{count_fmt}</strong> fiches recensées, toutes avec adresse email publiée.</p>
  <p class="sources">Source : API <code>api-lannuaire.service-public.fr</code>{api_date_txt}. Fusion et publication : justicelibre.org, Licence Ouverte 2.0.</p>
</section>

<main class="wrap">

<section class="block">
  <h2>Liste complète</h2>
  <p class="intro">Recherche libre par nom, ville, adresse email ou téléphone. Par défaut, {step} fiches sont affichées ; utilisez les boutons ci-dessous pour charger la suite. Les données restent servies en HTML brut, elles restent donc indexables et lisibles sans JavaScript.</p>

  <div class="filters">
    <input type="text" id="q" placeholder="Rechercher: nom, ville, mail, téléphone…" autocomplete="off">
    <span class="count" id="count"></span>
  </div>

  <div class="wrap-tbl"><div class="tbl-scroll">
    <table class="data" id="tbl">
      <thead><tr>
        <th class="no-sort">Catégorie</th>
        <th class="no-sort">Nom / Organisme</th>
        <th class="no-sort">Adresse électronique</th>
        <th class="no-sort">Contact</th>
        <th class="no-sort"></th>
      </tr></thead>
      <tbody id="tbody">
"""

SUB_TEMPLATE_FOOT = """      </tbody>
    </table>
  </div></div>

  <div class="paging" id="paging">
    <span id="pageStatus"></span>
    <button type="button" id="btnMore" class="btn btn-small btn-secondary">Afficher les {step} suivantes</button>
    <button type="button" id="btnAll" class="btn btn-small btn-secondary">all</button>
  </div>
</section>

</main>

<footer class="foot">
  justicelibre.org · <a href="/">Accueil</a> · <a href="/annuaire.html">Annuaire général</a> · <a href="/ressources.html">Ressources</a> · <a href="https://github.com/Dahliyaal/justicelibre">GitHub</a> · Licence Ouverte 2.0 (Etalab).
</footer>

<script>
(function(){
  var STEP = {step};
  var TOTAL = {total};
  var tbody = document.getElementById('tbody');
  var rows  = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
  var q     = document.getElementById('q');
  var count = document.getElementById('count');
  var btnMore = document.getElementById('btnMore');
  var btnAll  = document.getElementById('btnAll');
  var status  = document.getElementById('pageStatus');
  var visibleLimit = STEP;
  var lastQuery = '';

  function fmtN(n){ return String(n).replace(/\\B(?=(\\d{3})+(?!\\d))/g, ' '); }

  function apply(){
    var query = q.value.trim().toLowerCase();
    var matched = 0, shown = 0;
    var searching = query.length > 0;
    for (var i = 0; i < rows.length; i++){
      var row = rows[i];
      var visible;
      if (searching){
        var text = row.textContent.toLowerCase();
        if (text.indexOf(query) !== -1){ matched++; visible = true; }
        else visible = false;
      } else {
        visible = (i < visibleLimit);
        if (visible) shown++;
      }
      row.style.display = visible ? '' : 'none';
    }
    if (searching){
      count.textContent = fmtN(matched) + ' / ' + fmtN(TOTAL) + ' fiches';
      status.textContent = 'Recherche active';
      btnMore.disabled = true;
      btnAll.disabled = true;
    } else {
      count.textContent = fmtN(Math.min(visibleLimit, TOTAL)) + ' / ' + fmtN(TOTAL) + ' fiches';
      status.textContent = 'Affichage: ' + fmtN(Math.min(visibleLimit, TOTAL)) + ' / ' + fmtN(TOTAL);
      btnMore.disabled = visibleLimit >= TOTAL;
      btnAll.disabled  = visibleLimit >= TOTAL;
    }
    lastQuery = query;
  }

  btnMore.addEventListener('click', function(){ visibleLimit = Math.min(visibleLimit + STEP, TOTAL); apply(); });
  btnAll .addEventListener('click', function(){ visibleLimit = TOTAL; apply(); });
  var timer;
  q.addEventListener('input', function(){ clearTimeout(timer); timer = setTimeout(apply, 180); });

  // Bouton "Signaler" : ouvre un modal (GitHub ou email), mail contact@ obfusqué
  function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  document.getElementById('tbody').addEventListener('click', function(e){
    var btn = e.target.closest('button.signal');
    if (!btn) return;
    e.preventDefault();
    var row = btn.closest('tr');
    var nom = btn.getAttribute('data-n') || '';
    var catEl = row.querySelector('td.type .badge');
    var cat = catEl ? catEl.textContent.trim() : '';
    var mails = Array.prototype.map.call(row.querySelectorAll('td.mail a[href^="mailto:"]'), function(a){
      return a.getAttribute('href').replace(/^mailto:/, '');
    });
    var to   = 'contact' + String.fromCharCode(64) + 'justicelibre.org';
    var subj = 'Adresse à signaler : ' + nom;
    var body = [
      'Fiche : '      + nom,
      'Catégorie : '  + cat,
      'Adresse(s) : ' + mails.join(', '),
      '',
      'Motif du signalement (adresse morte, changement, autre) :',
      ''
    ].join('\\n');
    var ghHref = 'https://github.com/Dahliyaal/justicelibre/issues/new?title=' + encodeURIComponent('Signalement annuaire : ' + nom) + '&body=' + encodeURIComponent(body);
    var overlay = document.createElement('div');
    overlay.className = 'jl-modal-overlay';
    overlay.innerHTML = '<div class="jl-modal" role="dialog" aria-modal="true">'
      + '<button type="button" class="jl-modal-close" aria-label="Fermer">×</button>'
      + '<h3>Signaler une anomalie de contact</h3>'
      + '<p class="jl-modal-fiche"><strong>' + esc(nom) + '</strong><br><span class="jl-modal-sub">' + esc(cat) + ' · ' + mails.map(esc).join(', ') + '</span></p>'
      + '<p class="jl-modal-lead">Si cette adresse électronique n\\'est plus opérationnelle (coordonnées obsolètes, boîte de réception inactive ou changement de service), merci de nous en indiquer le motif. Nous procéderons à la correction dans les plus brefs délais.</p>'
      + '<p class="jl-modal-lead"><strong>Pour nous joindre :</strong></p>'
      + '<div class="jl-modal-actions">'
      +   '<a class="jl-modal-btn primary" href="' + ghHref + '" target="_blank" rel="noopener">Ouvrir un ticket GitHub</a>'
      + '</div>'
      + '<p class="jl-modal-hint">ou par email : <code>contact' + String.fromCharCode(64) + 'justicelibre.org</code></p>'
      + '</div>';
    document.body.appendChild(overlay);
    document.body.style.overflow = 'hidden';
    function close(){ overlay.remove(); document.body.style.overflow = ''; document.removeEventListener('keydown', onEsc); }
    function onEsc(ev){ if (ev.key === 'Escape') close(); }
    overlay.addEventListener('click', function(ev){ if (ev.target === overlay || ev.target.classList.contains('jl-modal-close')) close(); });
    document.addEventListener('keydown', onEsc);
  });

  // Theme toggle click handler
  var themeBtn = document.getElementById('themeToggle');
  if (themeBtn) themeBtn.addEventListener('click', function(){
    var html = document.documentElement;
    var isDark = html.getAttribute('data-theme') === 'dark' || (!html.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
    var next = isDark ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    try { localStorage.setItem('jl-theme', next); } catch(e){}
  });

  apply();
})();
</script>
</body>
</html>
"""

def _render_subpage(slug, label, desc, rows, source_note, cat_label=None):
    total = len(rows)
    api_date_txt = f" (capturé le {API_DATE})" if API_DATE else ""
    title = f"{label} - Annuaire · justicelibre.org"
    head = (SUB_TEMPLATE_HEAD
        .replace("{title}", esc(title))
        .replace("{desc}", esc(desc))
        .replace("{slug}", slug)
        .replace("{h1}", esc(label))
        .replace("{count_fmt}", _fmt_n(total))
        .replace("{step}", str(PAGE_STEP))
        .replace("{api_date_txt}", api_date_txt))
    body_rows = "\n".join(render_sub_row(r, i, PAGE_STEP, cat_label) for i, r in enumerate(rows))
    foot = SUB_TEMPLATE_FOOT.replace("{step}", str(PAGE_STEP)).replace("{total}", str(total))
    return head + body_rows + "\n" + foot

subpage_files = []
for slug, typ, label, desc in SUBPAGES:
    rows = sorted(by_type.get(typ, []), key=lambda r: r["nom"].lower())
    if not rows:
        continue
    # Une sous-page = une catégorie unique : on pré-échappe le label et
    # on l'inline dans chaque row (économise 1 lookup dict par row).
    html = _render_subpage(slug, label, desc, rows, "API annuaire.service-public.fr",
                           cat_label=esc(TYPE_LABELS.get(typ, typ)))
    path = OUT_SUB / f"{slug}.html"
    path.write_text(html, encoding="utf-8")
    subpage_files.append((slug, path, len(rows)))

# autres.html : tout ce qui reste
if autres_rows:
    html = _render_subpage(
        "autres",
        "Autres services publics",
        "Services publics de moindre volume non regroupés en sous-page dédiée : greffes des associations, commissariats, bureaux de douane, GRETA, CIDF, chambres d'agriculture, ADIL, PMI, etc. Source : API annuaire.service-public.fr.",
        autres_rows,
        "API annuaire.service-public.fr",
    )
    path = OUT_SUB / "autres.html"
    path.write_text(html, encoding="utf-8")
    subpage_files.append(("autres", path, len(autres_rows)))

# ─── 10. sitemap.xml ────────────────────────────────────────────────
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
existing_pages = [
    ("https://justicelibre.org/",                          "1.0"),
    ("https://justicelibre.org/annuaire.html",             "0.9"),
    ("https://justicelibre.org/search.html",               "0.8"),
    ("https://justicelibre.org/ressources.html",           "0.6"),
    ("https://justicelibre.org/tutoriel-piste.html",       "0.5"),
    ("https://justicelibre.org/stats.html",                "0.4"),
    ("https://justicelibre.org/mentions-legales.html",     "0.3"),
    ("https://justicelibre.org/confidentialite.html",      "0.3"),
]
sitemap_parts = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
for url, prio in existing_pages:
    sitemap_parts.append(f'  <url><loc>{url}</loc><lastmod>{today}</lastmod><priority>{prio}</priority></url>')
for slug, _, _ in subpage_files:
    sitemap_parts.append(
        f'  <url><loc>https://justicelibre.org/annuaire/{slug}.html</loc>'
        f'<lastmod>{today}</lastmod><priority>0.7</priority></url>'
    )
sitemap_parts.append('</urlset>')
REPO_SITEMAP.write_text("\n".join(sitemap_parts) + "\n", encoding="utf-8")

# ─── Bilan ──────────────────────────────────────────────────────────
print(f"[annuaire] juri: {len(juri_rows)} DILA + {len(manual_rows)} manuel + {len(api_rows)} API + {len(prada_rows)} PRADA")
print(f"[annuaire] index annuaire.html : {len(static_juri)} juri statiques + {len(prada_rows)} PRADA")
print(f"[annuaire] sous-pages : {len(subpage_files)}")
for slug, path, n in subpage_files:
    print(f"    /annuaire/{slug+'.html':30} {n:>6} fiches   {path.stat().st_size/1024:>8.1f} KB")
print(f"[annuaire] index size : {(OUT/'annuaire.html').stat().st_size/1024:.1f} KB")
print(f"[annuaire] sitemap    : {len(subpage_files) + len(existing_pages)} URLs")
