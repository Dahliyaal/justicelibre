"""SSR v2 — les pages serveur /decision/<source>/<id> et /loi/<code>/<num>
portées sur le normaliseur (web/styles/jl.css + web/jl.js + web/topbar.js).

Ce module NE REMPLACE PAS ssr.py : il l'importe. Tout ce qui relève du
référencement (title, description, canonical %-encodé, OpenGraph, Twitter,
JSON-LD LegalCase / Legislation) est calculé par les MÊMES fonctions que
ssr.py, pour qu'aucune page ne change d'adresse canonique ni de titre en
basculant. Ce qui change, c'est le CORPS de la page : l'assemblage de
`web/maquettes/decision-jl.html` (bande d'identité, onglets Texte / Dossier,
sommaire officiel étiqueté, textes visés sourcés, chronologie sourcée,
« cité par », bloc honnêteté, imprimante, « Copier pour un LLM »).

Branchement : `JL_SSR_V2=1` dans l'environnement de token_server.py.
Rapport : scratchpad/audit/v2_ssr_13sept.md

RÈGLES TENUES ICI
  - Tout le texte est dans le HTML : aucun appel d'API à l'ouverture.
  - Aucun style en ligne (les classes viennent de jl.css).
  - Trois <script> seulement : le résolveur de thème anti-flash, le JSON-LD,
    et le bloc de données #jl-page. jl.css / jl.js / topbar.js sont chargés
    par <link> et <script src> avec ?v=.
  - On n'affiche une ligne que si le champ existe. Jamais « other ».
  - Aucun résumé fabriqué : sommaire officiel ou rien.
  - Provenance écrite à côté de chaque information dérivée.
"""
from __future__ import annotations

import json as _json
import re
from urllib.parse import quote

from sources import citations as _citations

# ── Tout le head SEO et les helpers de ssr.py sont RÉUTILISÉS TELS QUELS ──
# (canonical, titres, descriptions, JSON-LD, bandeaux) : c'est la garantie
# que la bascule v2 ne touche pas au référencement.
from ssr import (                                    # noqa: F401
    BASE_URL, BULK_SOURCES, SITE_NAME, SOURCE_LABELS, _LANG_NAMES,
    _cached_decision_url, _cached_law_url, _canonical, _clean_dila_text,
    _format_fr_date, _jsonld_embed, _official_source_from_pattern,
    _source_host, _strip, esc,
)
import datetime as _dt

ASSET_V = "20260913"          # ?v= des trois fichiers du normaliseur

# ─────────────────────────────────────────────────────────────────────────
#  HEAD commun
# ─────────────────────────────────────────────────────────────────────────

_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=DM+Serif+Display:ital@0;1&'
    'family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&'
    'family=JetBrains+Mono:wght@400;500&display=swap">'
)

# Le seul script inline autorisé hors données : il pose data-theme AVANT le
# premier rendu. Sans lui la page clignote en blanc en thème sombre. Même
# dispositif que decision-jl.html:23-25 et que les 8 pages de production.
_THEME_RESOLVER = (
    "<script>(function(){try{var t=localStorage.getItem('jl-theme')"
    "||localStorage.getItem('hub-theme');"
    "if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;}"
    "catch(e){}})();</script>"
)


def _head(title_seo: str, desc: str, canonical: str, og_title: str,
          jsonld_str: str) -> str:
    """Head identique en substance à celui de ssr.py, feuilles v2 en plus."""
    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title_seo)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canonical)}">
<link rel="icon" type="image/svg+xml" href="/logo.svg">
<meta property="og:type" content="article">
<meta property="og:title" content="{esc(og_title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:locale" content="fr_FR">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{esc(og_title)}">
<meta name="twitter:description" content="{esc(desc)}">
<script type="application/ld+json">{jsonld_str}</script>
{_FONTS}
<link rel="stylesheet" href="/styles/jl.css?v={ASSET_V}">
{_THEME_RESOLVER}
<script defer src="/topbar.js?v={ASSET_V}"></script>
<script defer src="/jl.js?v={ASSET_V}"></script>"""


_RAIL = """  "rail": {
    "actif": "%s",
    "repliable": false,
    "cacheMobile": true,
    "mcp": "/ressources.html",
    "scopes": [
      {"k":"juris",    "icon":"scale",  "label":"Jurisprudence",         "href":"/hub.html#/juris"},
      {"k":"textes",   "icon":"book",   "label":"Textes",                "href":"/hub.html#/textes"},
      {"k":"travaux",  "icon":"hall",   "label":"Travaux préparatoires", "href":"/hub.html#/travaux"},
      {"k":"avis",     "icon":"chat",   "label":"Avis & doctrine",       "href":"/hub.html#/avis"},
      {"k":"annuaire", "icon":"people", "label":"Annuaire",              "href":"/hub.html#/annuaire"}
    ],
    "outils": [
      {"k":"citations", "icon":"check", "label":"Vérifier mes citations", "href":"/hub.html#/citations"}
    ]
  },"""


_URL_SURE_RE = re.compile(r"^https?://[A-Za-z0-9._~:/?#@!$&*+,;=%|\-]+$")
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _url_sure(u: str) -> str:
    """Une URL n'entre dans un <script> que si elle est indiscutablement inerte.

    Le bloc #jl-page est un `application/json`, donc du *raw text* pour le
    parseur HTML : un `</script>` dans une valeur refermerait la balise. On
    échappe (`_page_data`) ET on filtre à la source. Aucune donnée de texte
    libre (juridiction, numéro, intitulé) n'entre dans ce bloc : la ligne de
    référence est lue par jl.js dans le DOM (`#refL`), où elle est échappée.
    """
    u = (u or "").strip()
    return u if _URL_SURE_RE.match(u) else ""


def _page_data(actif: str, extra: dict) -> str:
    """Le bloc <script type="application/json" id="jl-page"> que jl.js lit."""
    body = _json.dumps(extra, ensure_ascii=False, indent=2)[1:-1].rstrip()
    inner = _RAIL % actif + (body if body.strip() else "")
    inner = (inner.replace("<", "\\u003c").replace(">", "\\u003e")
                  .replace("&", "\\u0026"))
    return ('<script type="application/json" id="jl-page">\n{\n'
            + inner + "\n}\n</script>")


_ICO_PRINT = ('<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
              'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
              'stroke-linejoin="round" aria-hidden="true"><path d="M6 9V3h12v6M6 '
              '18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 '
              '2h-2M6 14h12v7H6z"/></svg>')
_ICO_COPY = ('<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
             'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
             'stroke-linejoin="round" aria-hidden="true"><path d="M9 9h10v12H9zM5 '
             '15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/></svg>')

_BTN_PRINT = ('<button class="jl-bouton jl-bouton--icone" data-jl-print '
              'title="Imprimer ou enregistrer en PDF" '
              'aria-label="Imprimer ou enregistrer en PDF">' + _ICO_PRINT + '</button>')


def _shell(lang_attr: str, head: str, body: str) -> str:
    return (f'<!doctype html>\n<html lang="{lang_attr}" class="jl-dense">\n'
            f'<head>\n{head}\n</head>\n<body>\n{body}\n</body>\n</html>')


# ─────────────────────────────────────────────────────────────────────────
#  Texte : découpage, en-tête du greffe, titres, paragraphes numérotés
# ─────────────────────────────────────────────────────────────────────────

_PARA_NUM_RE = re.compile(r"^(\d{1,3})\.\s+(?=\S)")
# Fin de l'en-tête de greffe : la dernière ligne rituelle avant l'arrêt.
_GREFFE_END_RE = re.compile(r"AU NOM DU PEUPLE FRAN|R\s*É\s*P\s*U\s*B\s*L\s*I\s*Q\s*U\s*E",
                            re.IGNORECASE)
_PUNCT_FIN = ".;:,!?…»"


def _paragraphes(text: str) -> list[str]:
    """Texte brut → liste de paragraphes propres (jamais de reformulation)."""
    if not text:
        return []
    t = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    if "\n\n" not in t and "\n" in t:
        parts = [p.strip() for p in t.split("\n")]
    else:
        parts = [p.strip() for p in t.split("\n\n")]
    return [p for p in parts if p]


def _est_titre(p: str) -> bool:
    """Une ligne du texte qui joue le rôle de titre de section.

    Règle volontairement pauvre et VÉRIFIABLE : c'est un titre si la ligne
    est courte, tient en peu de mots, ne se termine par aucune ponctuation
    de phrase et ne commence pas par un numéro de paragraphe. On ne fabrique
    donc jamais d'intitulé : le libellé affiché est celui du texte, mot pour
    mot (« Faits et procédure », « Réponse de la Cour », « EN DROIT »…).
    """
    if not p or len(p) > 80 or "\n" in p:
        return False
    if p[-1] in _PUNCT_FIN:
        return False
    if _PARA_NUM_RE.match(p) or p[0].isdigit():
        return False
    if len(p.split()) > 9:
        return False
    # Une puce de liste (« a) », « 1° », « I. ») n'est pas un titre de section.
    if re.match(r"^[A-Za-z0-9]{1,3}\s*[.)°]\s", p):
        return False
    # Marqueurs techniques de HUDOC (« {signature_p_2} ») : ni titre, ni plan.
    if "{" in p or "}" in p:
        return False
    # Un titre de section commence par une majuscule.
    if not p[0].isupper():
        return False
    return bool(re.search(r"[A-Za-zÀ-ÿ]", p))


def _split_entete(paras: list[str]) -> tuple[list[str], list[str]]:
    """Sépare l'en-tête de mise en page du greffe du corps de la décision."""
    fin = -1
    for i, p in enumerate(paras[:18]):
        if _GREFFE_END_RE.search(p):
            fin = i
    if fin < 1:
        return [], paras
    return paras[:fin + 1], paras[fin + 1:]


def _slug(s: str, n: int = 40) -> str:
    """Ancre lisible : « Faits et procédure » → `faits-et-procedure`.

    Les accents sont translittérés, pas supprimés : sans cela l'ancre
    devenait `faits-et-proc-dure`, illisible dans la barre d'adresse.
    """
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s.lower().strip())
    return s.strip("-")[:n] or "s"


def _lier_articles(para: str, date: str) -> str:
    """Échappe le paragraphe et relie les articles cités.

    Les liens pointent vers la page INTERNE `/loi/<code>/<num>?date=<date de
    la décision>` : c'est la rédaction applicable à la date de l'arrêt, pas
    la rédaction d'aujourd'hui. (ssr.py liait vers Légifrance quand
    l'entrepôt répondait ; ici on garde le lecteur sur le site et on réserve
    Légifrance au bouton « source officielle ».)
    """
    hits = _citations.detect_citations(para)
    if not hits:
        return esc(para)
    out, cur = [], 0
    for code, num, (s, e) in hits:
        if s > cur:
            out.append(esc(para[cur:s]))
        href = f"/loi/{quote(code, safe='')}/{quote(num, safe='')}"
        if date:
            href += f"?date={quote(date, safe='')}"
        titre = f"{code} {num}"
        if date:
            titre += f" — rédaction en vigueur au {_format_fr_date(date)}"
        titre += " · repéré dans le texte"
        out.append(f'<a class="jl-artlink" href="{esc(href)}" '
                   f'title="{esc(titre)}">{esc(para[s:e])}</a>')
        cur = e
    if cur < len(para):
        out.append(esc(para[cur:]))
    return "".join(out)


def _rendre_texte(paras: list[str], date: str):
    """Corps de la décision → (html, entrées de sommaire, index des ancres).

    `ancres` : {(code, num): [(id_para, libellé)]} pour « Textes visés ».
    `dates`  : [(iso, libellé_fr, id_para)] pour la chronologie.
    """
    html_parts, toc, ancres, dates = [], [], {}, []
    for i, p in enumerate(paras):
        if _est_titre(p):
            pid = "s-" + _slug(p)
            html_parts.append(
                f'<h2 class="jl-titre jl-titre--nu" id="{esc(pid)}">{esc(p)}</h2>')
            toc.append((pid, p, "l2"))
            continue
        m = _PARA_NUM_RE.match(p)
        if m:
            n = m.group(1)
            pid = f"p{n}"
            corps = p[m.end():]
            body = _lier_articles(corps, date)
            html_parts.append(
                f'<p id="{esc(pid)}" class="jl-pn"><span class="jl-no">'
                f'<a href="#{esc(pid)}" title="lien vers le paragraphe {esc(n)}">'
                f'{esc(n)}.</a></span> {body}</p>')
            libelle = f"§ {n}"
            source_txt = corps
        else:
            pid = f"t{i}"
            html_parts.append(
                f'<p id="{esc(pid)}">{_lier_articles(p, date)}</p>')
            libelle = "texte"
            source_txt = p
        for code, num, _sp in _citations.detect_citations(source_txt):
            ancres.setdefault((code, num), [])
            if (pid, libelle) not in ancres[(code, num)]:
                ancres[(code, num)].append((pid, libelle))
        for iso, aff in _dates_du_texte(source_txt):
            dates.append((iso, aff, pid, libelle))
    return "\n".join(html_parts), toc, ancres, dates


_MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
            "août", "septembre", "octobre", "novembre", "décembre"]
_DATE_TXT_RE = re.compile(
    r"\b(1er|\d{1,2})\s+(" + "|".join(_MOIS_FR) + r")\s+((?:1[5-9]|20)\d{2})\b",
    re.IGNORECASE)


def _dates_du_texte(p: str) -> list[tuple[str, str]]:
    """Dates écrites en toutes lettres dans le texte. Rien d'autre.

    Aucune date n'est déduite, aucune juridiction n'est attachée : la
    chronologie ne dit que ce que la décision écrit noir sur blanc.
    """
    out = []
    for m in _DATE_TXT_RE.finditer(p):
        j = 1 if m.group(1).lower() == "1er" else int(m.group(1))
        mois = _MOIS_FR.index(m.group(2).lower()) + 1
        an = int(m.group(3))
        if not (1 <= j <= 31):
            continue
        out.append((f"{an:04d}-{mois:02d}-{j:02d}", m.group(0)))
    return out


# ─────────────────────────────────────────────────────────────────────────
#  Petits blocs
# ─────────────────────────────────────────────────────────────────────────

def _prov(texte: str, explication: str) -> str:
    """Note de provenance : ce qu'on affiche, et d'où ça vient."""
    return (f'<span class="jl-provenance" title="{esc(explication)}">'
            f'{esc(texte)}</span>')


def _avert(titre: str, corps: str) -> str:
    return (f'<p class="jl-warnp"><b>{esc(titre)}</b> {corps}</p>')


def _liste_json(v: str) -> list[str]:
    """`'["prescription civile"]'` → ['prescription civile'] ; `'[]'` → [].

    Piège relevé par l'inventaire des champs du 13 sept. (§1.2) : `abstrats`
    et `renvois` reviennent parfois comme la chaîne littérale « [] », qui
    compte comme non vide et ne porte rien.
    """
    v = (v or "").strip()
    if not v or v == "[]":
        return []
    if v.startswith("["):
        try:
            d = _json.loads(v)
            return [str(x).strip() for x in d if str(x).strip()]
        except Exception:
            pass
    return [v]


def _brut(v) -> str:
    """Judilibre code « other » quand la valeur n'est pas renseignée : ce
    n'est pas une information, on ne l'affiche pas (ssr.py:832)."""
    v = "" if v is None else str(v)
    return "" if v.strip().lower() in ("other", "none", "null") else v


def _bande(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return ""
    cells = "".join(
        f'<div><span class="jl-bande__k">{esc(k)}</span>{v}</div>'
        for k, v in rows if v)
    return f'<div class="jl-bande jl-bande--enligne">{cells}</div>'


# ─────────────────────────────────────────────────────────────────────────
#  PAGE DÉCISION
# ─────────────────────────────────────────────────────────────────────────

def render_decision(source: str, decision_id: str, data: dict) -> str:
    """Page HTML d'une décision, assemblage `decision-jl.html`.

    Signature publique identique à `ssr.render_decision`.
    """
    juri = data.get("juridiction", "") or ""
    date = data.get("date", "") or ""
    numero = data.get("numero") or data.get("numero_dossier") or ""
    titre_brut = data.get("titre") or data.get("title") or ""
    text = data.get("text") or data.get("full_text") or data.get("paragraph") or ""
    sommaire = data.get("sommaire") or ""
    abstrats = data.get("abstrats") or ""
    resume = data.get("resume") or ""
    renvois = data.get("renvois") or ""
    ecli = data.get("ecli", "") or ""
    formation = data.get("formation", "") or ""
    solution = _brut(data.get("solution", ""))
    nature = _brut(data.get("nature", ""))
    rapporteur = data.get("rapporteur", "") or ""
    commissaire_gvt = data.get("commissaire_gvt", "") or ""
    type_rec = _brut(data.get("type_rec", ""))
    publi_recueil = data.get("publi_recueil", "") or ""
    publi_bull = data.get("publi_bull", "") or ""
    nature_qualifiee = data.get("nature_qualifiee", "") or ""
    president = data.get("president", "") or ""
    avocats = data.get("avocats", "") or ""
    publication_ce = data.get("publication", "") or ""
    conclusion = data.get("conclusion", "") or ""
    importance = str(data.get("importance", "") or "")
    respondent = data.get("respondent", "") or ""
    article_conv = data.get("article", "") or ""
    liens_textes = data.get("liens_textes", "") or ""
    texte_integral = data.get("texte_integral", True)
    note_texte = data.get("note_texte", "") or ""
    text_lang = (data.get("text_lang") or "fr").lower()

    # ── Head SEO : STRICTEMENT le calcul de ssr.py ───────────────────────
    main_id = f"n° {numero}" if numero else titre_brut or f"Décision {decision_id}"
    title_h1_plain = f"{main_id} · {_format_fr_date(date)}" if date else main_id
    seo_ident = numero or (titre_brut[:90].strip() if titre_brut != juri else "")
    title_seo = f"{juri or seo_ident}, {seo_ident} {(_format_fr_date(date) or '').strip()} -{SITE_NAME}".strip()
    desc = _strip(text, 200) or f"{SOURCE_LABELS.get(source, '')} -{juri}".strip(" -")
    canonical = _canonical(source, decision_id)
    source_url = _cached_decision_url(decision_id, date or "") if decision_id else None

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
    jsonld_str = _jsonld_embed({k: v for k, v in jsonld.items() if v is not None})

    # ── Texte ────────────────────────────────────────────────────────────
    text = _clean_dila_text(text)
    sommaire = _clean_dila_text(sommaire)
    resume = _clean_dila_text(resume)
    paras = _paragraphes(text)
    entete, corps = _split_entete(paras)
    corps_html, toc, ancres, dates_txt = _rendre_texte(corps, date)
    if not corps_html:
        corps_html = '<p class="jl-muted"><em>Texte indisponible.</em></p>'

    # ── Bande d'identité : une ligne par champ EXISTANT ─────────────────
    rows: list[tuple[str, str]] = []
    if juri:
        rows.append(("Juridiction", esc(juri)))
    if formation:
        rows.append(("Formation", esc(formation)))
    if date:
        rows.append(("Date", esc(_format_fr_date(date))))
    if numero:
        rows.append(("Numéro", f'<span class="jl-mono">{esc(numero)}</span>'))
    if ecli:
        rows.append(("ECLI", f'<span class="jl-mono">{esc(ecli)}</span>'))
    if nature_qualifiee:
        rows.append(("Nature", esc(nature_qualifiee)))
    elif nature:
        rows.append(("Nature", esc(nature)))
    if type_rec:
        rows.append(("Type de recours", esc(type_rec)))
    if solution:
        rows.append(("Solution",
                     f'<span class="jl-pastille jl-pastille--ok">{esc(solution)}</span> '
                     + _prov("métadonnées", "Champ « solution » servi par l'API, "
                                            "non déduit du texte.")))
    if conclusion:
        rows.append(("Conclusion", esc(conclusion.replace(";", " ; "))))
    if article_conv:
        rows.append(("Articles en cause", esc(article_conv.replace(";", " ; "))))
    if respondent:
        rows.append(("État défendeur", f'<span class="jl-mono">{esc(respondent)}</span>'))
    if importance:
        _imp = {"1": "1 (arrêt de principe)", "2": "2", "3": "3",
                "4": "4 (faible)"}.get(importance, importance)
        rows.append(("Importance HUDOC", esc(_imp)))
    if president:
        rows.append(("Président", esc(president)))
    if rapporteur:
        rows.append(("Rapporteur", esc(rapporteur)))
    if commissaire_gvt:
        rows.append(("Rapporteur public", esc(commissaire_gvt)))
    if avocats:
        rows.append(("Avocats", esc(avocats)))
    if publication_ce:
        rows.append(("Publication", esc(publication_ce)))
    if publi_recueil:
        rows.append(("Publication", esc({"A": "Recueil Lebon", "B": "Tables Lebon",
                                         "C": "Inédit"}.get(publi_recueil, publi_recueil))))
    elif publi_bull == "oui":
        rows.append(("Publication", "Bulletin Cass."))
    bande = _bande(rows)

    # ── Titre ────────────────────────────────────────────────────────────
    if numero:
        # Le n° de pourvoi est la signature de l'arrêt : serif italique teal.
        h1 = (esc(_format_fr_date(date)) + ", " if date else "") + \
             f'n° <em>{esc(numero)}</em>'
    else:
        h1 = esc(titre_brut) or f"Décision {esc(decision_id)}"
        if date:
            h1 += f' <em>· {esc(_format_fr_date(date))}</em>'
    kicker = " · ".join(x for x in (juri, formation) if x) or \
        SOURCE_LABELS.get(source, source)

    # ── Barre de référence copiable ──────────────────────────────────────
    ref_long = ", ".join(x for x in (
        juri, formation, _format_fr_date(date) if date else "",
        f"n° {numero}" if numero else "", ecli,
        "publié au Bulletin" if publi_bull == "oui" else "",
    ) if x)
    ref_court = ", ".join(x for x in (
        juri, _format_fr_date(date) if date else "",
        f"n° {numero}" if numero else "") if x)
    cta = ""
    if source_url:
        cta = (f'<a class="jl-bouton jl-bouton--cta" data-align="fin" '
               f'href="{esc(source_url)}" target="_blank" '
               f'rel="external noopener nofollow">{esc(_source_host(source_url))} →</a>')
    refbar = (
        '<div class="jl-refbar"><span class="jl-surtitre">Référence</span>'
        f'<code id="refL" class="jl-mono">{esc(ref_long)}</code>'
        '<button class="jl-bouton jl-bouton--ghost jl-bouton--sm" data-copy="refL">copier</button>'
        f'<code id="refC" hidden>{esc(ref_court)}</code>'
        '<button class="jl-bouton jl-bouton--ghost jl-bouton--sm" data-copy="refC">courte</button>'
        '<span class="jl-copyok" data-copy-ok aria-live="polite"></span>'
        + cta + '</div>')

    # ── Avertissements honnêtes ──────────────────────────────────────────
    avertissements = ""
    if text_lang and text_lang != "fr":
        nom = _LANG_NAMES.get(text_lang, text_lang)
        deepl = "https://www.deepl.com/translator#" + \
            (text_lang if text_lang in _LANG_NAMES else "en") + "/fr/"
        avertissements += _avert(
            f"Texte original en {nom}.",
            "La version française de cette décision n'a pas été publiée. "
            f'Vous pouvez le traduire via un service externe : <a href="{esc(deepl)}" '
            'target="_blank" rel="external noopener">DeepL ↗</a> '
            "(coller le texte ci-dessous).")
    if texte_integral is False:
        avertissements += _avert(
            "Texte intégral : non.",
            esc(note_texte or "Nous n'avons que le sommaire ou l'analyse de cette "
                              "décision, pas son texte intégral.")
            + " La page ne fera jamais passer un résumé pour la décision.")
    if decision_id and re.match(r"^(?:DCE|DCAA|DTA|ORTA)_", decision_id):
        avertissements += _avert(
            "Source : open data du Conseil d'État",
            "loi pour une République numérique du 7 octobre 2016, art. 20-21. "
            "Cette décision n'est pas publiée au Recueil Lebon ; Légifrance ne "
            "l'indexe donc pas.")

    # ── Panneau TEXTE ────────────────────────────────────────────────────
    somm_html = ""
    if sommaire.strip():
        mat = _liste_json(abstrats)
        chips = ""
        if mat:
            chips = ('<p class="jl-somm__m"><span class="jl-surtitre">Matière</span> '
                     + " ".join(
                         f'<a class="jl-chip" href="/search.html?q={quote(m)}">{esc(m)}</a>'
                         for m in mat)
                     + " " + _prov("abstrats · DILA",
                                   "Plan de classement (champ « abstrats » du flux DILA).")
                     + '</p>')
        somm_html = (
            '<section id="sommaire-officiel" class="jl-somm">'
            '<h2 class="jl-surtitre jl-surtitre--flex">Sommaire officiel '
            + _prov("sommaire officiel · DILA",
                    "Sommaire rédigé par la juridiction et publié avec la décision "
                    "(champ « sommaire » du flux DILA / Judilibre). "
                    "Ce n'est pas une synthèse générée.")
            + '</h2>'
            f'<p class="jl-somm__t">{esc(sommaire.strip())}</p>' + chips + '</section>')
        toc.insert(0, ("sommaire-officiel", "Sommaire officiel", "l2"))

    entete_html = ""
    if entete:
        entete_html = (
            '<details class="jl-fold jl-entete-fold" id="entete">'
            '<summary class="jl-fold__sum">En-tête officiel de la décision '
            '<span class="jl-muted">(mise en page du greffe, déjà reprise dans la '
            'bande d\'identité)</span></summary>'
            f'<div class="jl-entete">{esc(chr(10).join(entete))}</div></details>')
        toc.insert(1 if somm_html else 0, ("entete", "En-tête de la décision", "l2"))

    toc_html = ""
    if toc:
        # Un plan de plus de 30 entrées n'est plus un plan : on le coupe plutôt
        # que de fabriquer une colonne aussi longue que l'arrêt.
        toc_html = ('<nav class="jl-toc" id="toc" aria-label="Plan de la décision">'
                    + "".join(f'<a href="#{esc(i)}" class="{c}">{esc(lbl)}</a>'
                              for i, lbl, c in toc[:30]) + '</nav>')

    pane_texte = ('<div class="jl-pane jl-pane--texte" id="texte"><div class="jl-lecture">'
                  '<div class="jl-txt">' + somm_html + entete_html + corps_html
                  + '</div>' + toc_html + '</div></div>')

    # ── Panneau DOSSIER ──────────────────────────────────────────────────
    pane_fiche = ('<div class="jl-pane jl-pane--fiche" id="fiche">'
                  '<div class="jl-grille-2">'
                  + _sec_textes_vises(liens_textes, ancres, date)
                  + _sec_chronologie(dates_txt, date, juri, source)
                  + _sec_analyses(abstrats, resume, renvois)
                  + _sec_cite_par(numero, ecli, ancres, date)
                  + '</div></div>')

    dossier = (
        '<div class="jl-dossier">'
        '<input class="jl-tab" type="radio" name="tab" id="t-texte" checked>'
        '<input class="jl-tab" type="radio" name="tab" id="t-fiche">'
        '<div class="jl-onglets" role="tablist">'
        '<label for="t-texte">Texte</label><label for="t-fiche">Dossier</label></div>'
        '<div class="jl-panes">' + pane_texte + pane_fiche + '</div></div>')

    # ── Pied : provenance ────────────────────────────────────────────────
    bulk_label, bulk_url = BULK_SOURCES.get(source, ("", ""))
    pied = ('<footer class="jl-pied">Source : '
            + esc(SOURCE_LABELS.get(source, source))
            + (f', archive <a href="{esc(bulk_url)}" rel="external noopener">'
               f'{esc(bulk_label)}</a>' if bulk_url else "")
            + f', identifiant <span class="jl-mono">{esc(decision_id)}</span>, '
              'Licence Ouverte 2.0. JusticeLibre est une copie miroir indexée'
            + (f' ; la version qui fait foi est celle publiée sur '
               f'<a href="{esc(source_url)}" rel="external noopener nofollow">'
               f'{esc(_source_host(source_url))}</a>.' if source_url else ".")
            + '</footer>')

    jl_page = _page_data("juris", {
        "onglets": {"texte": "t-texte", "fiche": "t-fiche"},
        "retourRecherche": True,
        # Rien que des URL vérifiées et une date validée : la ligne d'identité
        # est lue par jl.js dans le DOM (#refL), pas passée par ce bloc.
        "llm": {
            "url": _url_sure(canonical),
            "sourceUrl": _url_sure(source_url or ""),
            "licence": "Licence Ouverte 2.0",
            "dateRedaction": _format_fr_date(date) if _ISO_RE.match(date or "") else "",
        },
    })

    body = f"""<div data-topbar-mount></div>
<div class="jl-app">
<nav class="jl-rail jl-rail--cache" data-jl-rail aria-label="Chercher dans"></nav>
<main class="jl-body">
<div class="jl-fil" id="backrow" hidden><a href="/search.html" id="backlink">← Résultats de la recherche</a></div>
<div class="jl-kicker">{esc(kicker)}</div>
<div class="jl-titrerow"><h1 class="jl-titre jl-titre--h1">{h1}</h1>
<div class="jl-actions">{_BTN_PRINT}<button class="jl-bouton jl-bouton--ghost" data-jl-llm title="Copie un bloc texte structuré : référence, ECLI, URL, sommaire officiel, textes visés, texte intégral, provenance. À coller dans un assistant.">{_ICO_COPY}<span data-jl-llm-label>Copier pour un LLM</span></button></div></div>
{bande}
{refbar}
{avertissements}
{dossier}
{pied}
</main>
{jl_page}
</div>"""
    return _shell("fr", _head(title_seo, desc, canonical, title_h1_plain, jsonld_str), body)


# ── Sections du panneau « Dossier » ──────────────────────────────────────

def _sec_textes_vises(liens_textes: str, ancres: dict, date: str) -> str:
    """Textes visés. Le visa LEGI structuré d'abord, la regex ensuite."""
    blocs = []
    visa = (liens_textes or "").strip()
    if visa:
        blocs.append(
            '<div class="jl-vise jl-vise--encadre"><div class="jl-vise__t">'
            + esc(visa) + '</div><div class="jl-vise__d">'
            + _prov("visa LEGI",
                    "Champ « liens_textes » : visas structurés fournis avec la "
                    "décision par le flux LEGI / DILA.")
            + '</div></div>')
    for (code, num), refs in ancres.items():
        href = f"/loi/{quote(code, safe='')}/{quote(num, safe='')}"
        if date:
            href += f"?date={quote(date, safe='')}"
        cites = " · ".join(f'<a href="#{esc(pid)}">{esc(lbl)}</a>'
                           for pid, lbl in refs[:8])
        redac = ""
        if date:
            redac = ('<span class="jl-rd" title="lien vers la rédaction en vigueur '
                     'à la date de la décision">rédaction au '
                     + esc(_format_fr_date(date)) + '</span>')
        blocs.append(
            f'<div class="jl-vise jl-vise--encadre"><div class="jl-vise__t">'
            f'<a class="jl-artlink" href="{esc(href)}">article {esc(num)}</a> '
            f'<span class="jl-mono jl-muted">{esc(code)}</span></div>'
            f'<div class="jl-vise__d">{redac}'
            + _prov("repéré dans le texte",
                    "Aucun visa structuré exploitable : l'article est repéré par "
                    "expression régulière « article X du code Y » dans le texte "
                    "de la décision (sources/citations.py).")
            + (f'<span>cité : {cites}</span>' if cites else "")
            + '</div></div>')
    if not blocs:
        return ('<section id="textes-vises">'
                '<h2 class="jl-surtitre jl-surtitre--flex">Textes visés</h2>'
                '<p class="jl-empty">Aucun article de code repéré dans le texte, '
                'et aucun visa structuré fourni pour cette décision.</p></section>')
    return ('<section id="textes-vises">'
            '<h2 class="jl-surtitre jl-surtitre--flex">Textes visés '
            f'<span class="jl-muted" data-align="fin">{len(blocs)}</span></h2>'
            + "".join(blocs)
            + '<p class="jl-note-fin">Chaque lien ouvre l\'article dans sa rédaction '
              'en vigueur à la date de la décision.</p></section>')


def _sec_chronologie(dates_txt, date: str, juri: str, source: str) -> str:
    """Chronologie : rien que les dates lues dans le texte ou les métadonnées.

    Aucune juridiction n'est attachée à une date du texte : le texte ne dit
    pas toujours qui a statué, et on n'invente pas.
    """
    vus, items = set(), []
    if date:
        items.append((date, _format_fr_date(date),
                      esc(juri) if juri else "", "", "métadonnées",
                      "Champ « date » servi par l'API pour cette décision.", True))
        vus.add(date)
    for iso, aff, pid, lbl in dates_txt:
        if iso in vus or iso == date:
            continue
        vus.add(iso)
        items.append((iso, aff, "", pid, "repéré dans le texte",
                      "Date écrite en toutes lettres dans le texte de la décision. "
                      "La juridiction n'est pas indiquée : le texte ne la nomme "
                      "pas toujours, et on ne la déduit pas.", False))
    if len(items) <= 1 and not dates_txt:
        return ('<section id="chronologie">'
                '<h2 class="jl-surtitre jl-surtitre--flex">Chronologie</h2>'
                '<p class="jl-empty">Aucune date datable dans le texte.</p></section>')
    items.sort(key=lambda x: x[0], reverse=True)
    lis = []
    for iso, aff, j, pid, ptxt, pexp, cur in items[:24]:
        cls = ' class="is-cur"' if cur else ''
        lis.append(
            f'<li{cls}>'
            f'<div class="jl-chrono__d">{esc(aff)}</div>'
            + (f'<div class="jl-chrono__j">{j}</div>' if j else "")
            + '<div class="jl-chrono__w">' + _prov(ptxt, pexp)
            + (f' <a href="#{esc(pid)}">voir</a>' if pid else "") + '</div></li>')
    return ('<section id="chronologie">'
            '<h2 class="jl-surtitre jl-surtitre--flex">Chronologie '
            + _prov("texte + métadonnées",
                    "Les étapes structurées (décision attaquée, timeline) ne sont "
                    "pas servies par l'API : les dates sont lues dans la décision "
                    "elle-même, avec renvoi au paragraphe.")
            + '</h2><ul class="jl-chrono">' + "".join(lis) + '</ul></section>')


def _sec_analyses(abstrats: str, resume: str, renvois: str) -> str:
    """Plan de classement, résumé et renvois : servis tels quels, sourcés."""
    out = []
    mat = _liste_json(abstrats)
    if mat:
        out.append('<p><b>Plan de classement</b> ' +
                   _prov("abstrats · DILA", "Champ « abstrats » du flux DILA.") +
                   '<br>' + esc(" · ".join(mat)) + '</p>')
    if (resume or "").strip():
        out.append('<p><b>Résumé officiel</b> ' +
                   _prov("resume · DILA", "Champ « resume » du flux DILA, rédigé "
                                          "par la juridiction.") +
                   '<br>' + esc(resume.strip()) + '</p>')
    rv = _liste_json(renvois)
    if rv:
        out.append('<p><b>Renvois jurisprudentiels</b> ' +
                   _prov("renvois · DILA", "Champ « renvois » du flux DILA.") +
                   '<br>' + esc(" ".join(rv)) + '</p>')
    if not out:
        return ""
    return ('<section id="analyses">'
            '<h2 class="jl-surtitre jl-surtitre--flex">Analyse officielle</h2>'
            + "".join(out) + '</section>')


def _sec_cite_par(numero: str, ecli: str, ancres: dict, date: str) -> str:
    q = numero or ecli
    cite_par = ""
    if q:
        cite_par = ('<p><b>Cité par</b> : <a href="/search.html?q='
                    + quote(f'"{q}"') + '">chercher les décisions qui citent '
                    + esc(q) + '</a> '
                    + _prov("recherche lexicale",
                            "Recherche plein texte sur le numéro dans le corpus. "
                            "Le nombre n'est pas calculé à l'ouverture de la page "
                            "(aucun appel d'API).") + '</p>')
    cite = ""
    if ancres:
        liens = []
        for (code, num) in list(ancres)[:12]:
            href = f"/loi/{quote(code, safe='')}/{quote(num, safe='')}"
            if date:
                href += f"?date={quote(date, safe='')}"
            liens.append(f'<a class="jl-artlink" href="{esc(href)}">art. '
                         f'{esc(num)} {esc(code)}</a>')
        cite = '<p><b>Cite</b> : ' + ", ".join(liens) + '</p>'
    return ('<section id="cite-par">'
            '<h2 class="jl-surtitre jl-surtitre--flex">Cité par · Cite</h2>'
            + cite_par + cite
            + '<div class="jl-honnetete" data-espace="haut">Pas de « décisions '
              'similaires » ni de nombre de citations : nous n\'avons pas encore de '
              'méthode fiable pour les calculer côté serveur, donc rien n\'est '
              'affiché plutôt qu\'une liste approximative. Les parties et la '
              'décision attaquée ne sont pas non plus affichées : ces champs '
              'existent au schéma DILA mais ne sont pas servis par l\'API.'
              '</div></section>')


# ─────────────────────────────────────────────────────────────────────────
#  PAGE ARTICLE DE LOI
# ─────────────────────────────────────────────────────────────────────────

def _statut(etat: str, date_fin: str) -> str:
    """Même arbitrage qu'ssr.render_law (ssr.py:1087-1096).

    Un article n'est « en vigueur » que si son état le dit ET que sa fin de
    validité n'est pas passée. 26 abrogés testés, 26 affichés en vigueur
    avant le 10/09/2026.
    """
    fin_passee = bool(date_fin) and date_fin != "2999-01-01" and \
        date_fin <= _dt.date.today().isoformat()
    e = (etat or "").upper()
    if e in ("ABROGE", "PERIME", "TRANSFERE", "ANNULE") or fin_passee:
        return "abroge"
    if e == "ABROGE_DIFF":
        return "abroge_diff"
    if e in ("VIGUEUR", "VIGUEUR_DIFF", "MODIFIE", "MODIFIE_MORT_NE") or not e:
        return "vigueur"
    return "inconnu"


def _subline_statut(statut: str, date_debut: str, date_fin: str,
                    etat: str, note: str) -> str:
    """La phrase sous le titre : dit d'abord si l'article s'applique.

    Port sans style en ligne de `ssr._subline_statut` (ssr.py:1012). Les
    couleurs viennent de jl.css (§29 : rouge atténué pour l'abrogé).
    """
    deb = esc(_format_fr_date(date_debut)) if date_debut else ""
    fin = esc(_format_fr_date(date_fin)) if date_fin and date_fin != "2999-01-01" else ""
    if statut == "abroge":
        libelle = "Article abrogé" if (etat or "").upper() in ("ABROGE", "") \
            else f"Article {esc((etat or '').lower())}"
        periode = f" — version en vigueur du {deb} au {fin}" if (deb and fin) \
            else (f" le {fin}" if fin else "")
        out = (f'<p class="jl-lead jl-statut jl-statut--abroge">⚠ {libelle}{periode}. '
               f"Ce texte ne s'applique plus.</p>")
    elif statut == "abroge_diff":
        out = (f'<p class="jl-lead jl-statut">Article en vigueur depuis le {deb}'
               f'{(" — abrogation à effet du " + fin) if fin else ""}.</p>')
    elif statut == "vigueur":
        out = (f'<p class="jl-lead jl-statut">Article en vigueur'
               f'{(" depuis le " + deb) if deb else ""}.</p>')
    else:
        out = (f'<p class="jl-lead jl-statut">Article — état : '
               f'{esc(etat or "inconnu")}{(", depuis le " + deb) if deb else ""}.</p>')
    if note:
        out += f'<p class="jl-lead jl-statut__note">{esc(note)}</p>'
    return out


def render_law(code: str, num: str, data: dict) -> str:
    """Page HTML d'un article de loi, dans la charte de web/v2/article.html.

    Signature publique identique à `ssr.render_law`.
    """
    titre_texte = data.get("titre_texte") or data.get("titre_section") or ""
    titre_section = data.get("titre_section") or ""
    texte = data.get("texte", "") or ""
    etat = data.get("etat", "") or ""
    date_debut = data.get("date_debut", "") or ""
    date_fin = data.get("date_fin", "") or ""
    note = data.get("note", "") or ""
    nota = data.get("nota", "") or ""
    source_url = data.get("source_url", "") or ""
    legitext = data.get("legitext", "") or ""
    legiarti = data.get("legiarti", "") or ""
    statut = _statut(etat, date_fin)

    # ── Head SEO : STRICTEMENT le calcul de ssr.render_law ───────────────
    code_label = titre_texte or code
    title_h1 = f"Article {num}"
    title_seo = f"Article {num} -{code_label} -{SITE_NAME}"
    desc = _strip(texte, 200) or f"Article {num} du {code_label}"
    canonical = f"{BASE_URL}/loi/{code}/{num}"
    og_title = title_h1 + " -" + code_label

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
        "legislationLegalForce": {"vigueur": "InForce", "abroge": "NotInForce",
                                  "abroge_diff": "InForce"}.get(statut, "PartiallyInForce"),
        "sameAs": source_url or None,
    }
    jsonld_str = _jsonld_embed({k: v for k, v in jsonld.items() if v is not None})

    # ── Corps ────────────────────────────────────────────────────────────
    alineas = "".join(
        f'<p class="jl-alin"><span class="jl-al">{i}.</span> {esc(p)}</p>'
        for i, p in enumerate(_paragraphes(texte), 1)) \
        or '<p class="jl-empty">Texte indisponible.</p>'
    nota_html = (f'<div class="jl-nota"><b>Nota :</b> {esc(nota)}</div>') if nota else ""

    rows: list[tuple[str, str]] = [("Code", esc(code_label))]
    if titre_section:
        rows.append(("Rattachement", esc(titre_section)))
    if etat:
        rows.append(("État", esc(etat)))
    if date_debut:
        rows.append(("En vigueur depuis", esc(_format_fr_date(date_debut))))
    if date_fin and date_fin != "2999-01-01":
        rows.append(("Jusqu'au", esc(_format_fr_date(date_fin))))
    if legiarti:
        rows.append(("Identifiant",
                     f'<span class="jl-mono">{esc(legiarti)}</span>'))
    if legitext:
        rows.append(("Texte parent",
                     f'<span class="jl-mono">{esc(legitext)}</span>'))
    bande = _bande(rows)

    ref = f"article {num} du {code_label}" + \
        (f" (version du {_format_fr_date(date_debut)})" if date_debut else "")
    cta = ""
    if source_url:
        cta = (f'<a class="jl-bouton jl-bouton--cta" data-align="fin" '
               f'href="{esc(source_url)}" target="_blank" '
               f'rel="external noopener nofollow">{esc(_source_host(source_url))} →</a>')
    refbar = ('<div class="jl-refbar"><span class="jl-surtitre">Référence</span>'
              f'<code id="refL" class="jl-mono">{esc(ref)}</code>'
              '<button class="jl-bouton jl-bouton--ghost jl-bouton--sm" data-copy="refL">copier</button>'
              '<span class="jl-copyok" data-copy-ok aria-live="polite"></span>'
              + cta + '</div>')

    carte_href = f"/v2/article.html?code={quote(code, safe='')}&num={quote(num, safe='')}"
    carte = ('<section id="carte"><h2 class="jl-surtitre jl-surtitre--flex">'
             'Carte de l\'article</h2>'
             f'<p><a class="jl-bouton jl-bouton--ghost jl-bouton--sm" '
             f'href="{esc(carte_href)}">Carte de l\'article</a> '
             '<span class="jl-muted">page dynamique : le texte qui l\'a écrit, '
             'les textes pris pour lui, l\'historique des rédactions. '
             'Bientôt.</span></p>'
             '<div class="jl-honnetete" data-espace="haut">Cette page ne montre que '
             'la rédaction servie par l\'entrepôt. Les versions voisines, le plan '
             'complet du code au-dessus de l\'article et les décisions qui le citent '
             'existent en base mais ne sont pas encore servis par une route '
             'serveur.</div></section>')

    pied = ('<footer class="jl-pied">Source : base LEGI (Légifrance), archive '
            '<a href="https://echanges.dila.gouv.fr/OPENDATA/LEGI/" '
            'rel="external noopener">DILA, bulk LEGI (codes consolidés)</a>, '
            'Licence Ouverte 2.0. JusticeLibre est une copie miroir indexée ; la '
            'version qui fait foi est celle publiée sur '
            + (f'<a href="{esc(source_url)}" rel="external noopener nofollow">'
               'legifrance.gouv.fr</a>.' if source_url else "Légifrance.")
            + '</footer>')

    jl_page = _page_data("textes", {"toc": False, "retourRecherche": True})

    body = f"""<div data-topbar-mount></div>
<div class="jl-app">
<nav class="jl-rail jl-rail--cache" data-jl-rail aria-label="Chercher dans"></nav>
<main class="jl-body">
<div class="jl-fil" id="backrow" hidden><a href="/search.html" id="backlink">← Résultats de la recherche</a></div>
<div class="jl-titrerow"><h1 class="jl-titre jl-titre--h1 jl-titrepage">Article <em>{esc(num)}</em> · {esc(code_label)}</h1>
<div class="jl-actions">{_BTN_PRINT}</div></div>
{_subline_statut(statut, date_debut, date_fin, etat, note)}
{bande}
{refbar}
<article class="jl-carte">{alineas}{nota_html}</article>
{carte}
{pied}
</main>
{jl_page}
</div>"""
    return _shell("fr", _head(title_seo, desc, canonical, og_title, jsonld_str), body)


# ─────────────────────────────────────────────────────────────────────────
#  404 : on garde celles de ssr.py (non concernées par le mandat).
# ─────────────────────────────────────────────────────────────────────────
from ssr import render_decision_404, render_law_404  # noqa: E402,F401
