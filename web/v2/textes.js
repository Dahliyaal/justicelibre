/**
 * web/v2/textes.js — la PAGE « TEXTES » de la refonte v2.
 *
 * Aucun style ni script en ligne dans textes.html : tout le comportement est
 * ici, tous les composants partagés sont dans /styles/jl.css et /jl.js.
 *
 * Ce qu'elle reprend, et d'où :
 *   - barre réseau, états de source, pastille loader, « jamais aucun résultat
 *     si la source n'a pas répondu », pagination avec total/total_exact,
 *     extraits compactés  → web/v2/recherche.js:291-436, 449-636
 *   - fiche d'article (rédaction, état, plage de dates, nota, Légifrance daté,
 *     toutes les versions)                        → web/v2/recherche.js:753-817
 *   - table des 75 codes (LEGITEXT, libellé, abréviations), tri par SUJET,
 *     lecture d'un article par sa référence       → web/hub.html:411-575, 874-882
 *   - textes hors code : ministère (NOR) › nature › année
 *                                                 → web/hub.html:442-538
 *
 * ⛔ Règle qui gouverne tout ce fichier, comme la page de recherche : ne
 *    JAMAIS dire « aucun résultat » quand la source n'a pas répondu. Sur un
 *    site de droit, un faux négatif fait conclure qu'un texte n'existe pas.
 *
 * ⛔ Deuxième règle, propre aux textes : ne jamais résumer un article. Le
 *    texte est cité, jamais reformulé, et chaque information porte sa
 *    provenance (« LEGI · DILA »).
 */
(function () {
  'use strict';

  var API = (location.hostname === 'justicelibre.org') ? '' : 'https://justicelibre.org';
  /* La lecture d'un article ouvre la PAGE SERVEUR /loi/<sigle>/<num> : c'est
     elle que Google indexe, pas une vue JS (même choix que DECISION_BASE,
     recherche.js:25). En local, on pointe la prod. */
  var LOI_BASE = (location.hostname === 'justicelibre.org') ? '/loi' : 'https://justicelibre.org/loi';
  var PAGE = 30;

  var J, $, $$, esc;   /* renseignés au démarrage, quand JL est chargé */

  /* ═══════════════ 1. Les 75 codes servis ══════════════════════════════
     [sigle, LEGITEXT, libellé long, abréviations acceptées].
     - le SIGLE est l'identifiant attendu par /api/law et par /loi/<code>/<num>
       (sources/legi.py:17-104 SUPPORTED_CODES, :111-191 SUPPORTED_CODES_LEGITEXT) ;
     - le LEGITEXT est ce que les résultats de recherche renvoient
       (search_api.py:646 « legitext ») : c'est lui qui permet le chemin
       inverse résultat → page serveur ;
     - les abréviations viennent de web/hub.html:497-572, telles quelles. */
  var CODES = [
    ["CC","LEGITEXT000006070721","Code civil",["c. civ.", "cc", "cciv"]],
    ["CP","LEGITEXT000006070719","Code pénal",["c. pén.", "cp"]],
    ["CPC","LEGITEXT000006070716","Code de procédure civile",["c. pr. civ.", "cpc"]],
    ["CPP","LEGITEXT000006071154","Code de procédure pénale",["cpp"]],
    ["CT","LEGITEXT000006072050","Code du travail",["c. trav.", "ct", "ctrav"]],
    ["CSP","LEGITEXT000006072665","Code de la santé publique",["csp"]],
    ["CJA","LEGITEXT000006070933","Code de justice administrative",["cja"]],
    ["CGCT","LEGITEXT000006070633","Code général des collectivités territoriales",["cgct"]],
    ["CCom2","LEGITEXT000006070162","Code des communes (obsolète)",["ccom2", "code des communes (obsolète, remplacé par cgct)"]],
    ["CRPA","LEGITEXT000031366350","Code des relations entre le public et l'administration",["crpa", "relations public-administration"]],
    ["CPI","LEGITEXT000006069414","Code de la propriété intellectuelle",["cpi", "propriété intellectuelle"]],
    ["CASF","LEGITEXT000006074069","Code de l'action sociale et des familles",["action sociale et familles", "casf"]],
    ["CMF","LEGITEXT000006072026","Code monétaire et financier",["cmf", "monétaire et financier"]],
    ["C.com","LEGITEXT000005634379","Code de commerce",["c.com", "commerce"]],
    ["C.cons","LEGITEXT000006069565","Code de la consommation",["c.cons", "consommation"]],
    ["C.éduc","LEGITEXT000006071191","Code de l'éducation",["c.éduc", "éducation"]],
    ["CU","LEGITEXT000006074075","Code de l'urbanisme",["cu", "urbanisme"]],
    ["C.env","LEGITEXT000006074220","Code de l'environnement",["c.env", "environnement"]],
    ["CR","LEGITEXT000006071367","Code rural et de la pêche maritime",["cr", "rural et pêche maritime"]],
    ["CGI","LEGITEXT000006069577","Code général des impôts",["cgi", "code général des impôts (principal)"]],
    ["CESEDA","LEGITEXT000006070158","Code de l'entrée et du séjour des étrangers et du droit d'asile",["ceseda", "entrée/séjour étrangers"]],
    ["CSS","LEGITEXT000006073189","Code de la sécurité sociale",["css", "sécurité sociale"]],
    ["CCH","LEGITEXT000006074096","Code de la construction et de l'habitation",["cch", "construction et habitation"]],
    ["CTransp","LEGITEXT000023086525","Code des transports",["ctransp", "transports"]],
    ["CAss","LEGITEXT000006073984","Code des assurances",["assurances", "cass"]],
    ["CDef","LEGITEXT000006071307","Code de la défense",["cdef", "défense"]],
    ["CSI","LEGITEXT000025503132","Code de la sécurité intérieure",["csi", "sécurité intérieure"]],
    ["CEner","LEGITEXT000023983208","Code de l'énergie",["cener", "énergie"]],
    ["CCiné","LEGITEXT000020908868","Code du cinéma et de l'image animée",["cciné", "cinéma et image animée"]],
    ["CSport","LEGITEXT000006071318","Code du sport",["csport", "sport"]],
    ["CJF","LEGITEXT000006070249","Code des juridictions financières",["cjf", "juridictions financières"]],
    ["COJ","LEGITEXT000006071164","Code de l'organisation judiciaire",["coj", "organisation judiciaire"]],
    ["CPCE","LEGITEXT000006070987","Code des postes et des communications électroniques",["cpce", "postes et communications électroniques"]],
    ["CElec","LEGITEXT000006070239","Code électoral",["celec", "électoral"]],
    ["CGFP","LEGITEXT000044416551","Code général de la fonction publique",["cgfp", "général de la fonction publique"]],
    ["LPF","LEGITEXT000006069583","Livre des procédures fiscales",["lpf"]],
    ["CRoute","LEGITEXT000006074228","Code de la route",["croute", "route"]],
    ["CPatr","LEGITEXT000006074236","Code du patrimoine",["cpatr", "patrimoine"]],
    ["CMut","LEGITEXT000006074067","Code de la mutualité",["cmut", "mutualité"]],
    ["CPénit","LEGITEXT000045476241","Code pénitentiaire",["cpénit", "pénitentiaire"]],
    ["CCP","LEGITEXT000037701019","Code de la commande publique",["ccp", "commande publique"]],
    ["CAvCiv","LEGITEXT000006074234","Code de l'aviation civile",["aviation civile", "cavciv"]],
    ["CIBS","LEGITEXT000044595989","Code des impositions sur les biens et services",["cibs", "impositions des biens et services"]],
    ["CDouanes","LEGITEXT000006071570","Code des douanes",["cdouanes", "douanes"]],
    ["CForêt","LEGITEXT000025244092","Code forestier (nouveau)",["cforêt", "forestier (nouveau)"]],
    ["CG3P","LEGITEXT000006070299","Code général de la propriété des personnes publiques",["cg3p", "propriété des personnes publiques"]],
    ["CTou","LEGITEXT000006074073","Code du tourisme",["ctou", "tourisme"]],
    ["CSN","LEGITEXT000006071335","Code du service national",["csn", "service national"]],
    ["CRech","LEGITEXT000006071190","Code de la recherche",["crech", "recherche"]],
    ["CPortM","LEGITEXT000006074233","Code des ports maritimes",["cportm", "ports maritimes"]],
    ["CDE","LEGITEXT000006070208","Code du domaine de l'Etat",["cde", "domaine de l'état"]],
    ["CMin","LEGITEXT000023501962","Code minier (nouveau)",["cmin", "minier"]],
    ["CJM","LEGITEXT000006071360","Code de justice militaire",["cjm", "justice militaire"]],
    ["CExpr","LEGITEXT000006074224","Code de l'expropriation pour cause d'utilité publique",["cexpr", "expropriation"]],
    ["CVoir","LEGITEXT000006070667","Code de la voirie routière",["cvoir", "voirie routière"]],
    ["CJPM","LEGITEXT000039086952","Code de la justice pénale des mineurs",["cjpm", "justice pénale des mineurs"]],
    ["CArt","LEGITEXT000006075116","Code de l'artisanat",["artisanat", "cart"]],
    ["CPCMR","LEGITEXT000006070302","Code des pensions civiles et militaires de retraite",["cpcmr", "pensions civiles et militaires de retraite"]],
    ["CPCEx","LEGITEXT000025024948","Code des procédures civiles d'exécution",["cpcex", "procédures civiles d'exécution"]],
    ["CGIANII","LEGITEXT000006069569","Code général des impôts, annexe II",["cgi annexe ii", "cgianii"]],
    ["CGIANI","LEGITEXT000006069568","Code général des impôts, annexe I",["cgi annexe i", "cgiani"]],
    ["CGIANIII","LEGITEXT000006069574","Code général des impôts, annexe III",["cgi annexe iii", "cgianiii"]],
    ["CGIANIV","LEGITEXT000006069576","Code général des impôts, annexe IV",["cgi annexe iv", "cgianiv"]],
    ["CRurA","LEGITEXT000006071366","Code rural ancien (obsolète)",["crura", "rural (ancien)"]],
    ["CCNC","LEGITEXT000006070300","Code des communes de la Nouvelle-Calédonie",["ccnc", "communes de la nouvelle-calédonie"]],
    ["CMinA","LEGITEXT000006071785","Code minier (ancien)",["cmina", "minier (ancien)"]],
    ["CFAS","LEGITEXT000006072637","Code de la famille et de l aide sociale (obsolète)",["cfas", "famille et aide sociale (ancien)"]],
    ["CDouMay","LEGITEXT000006071645","Code des douanes de Mayotte",["cdoumay", "douanes de mayotte"]],
    ["CDPFNav","LEGITEXT000006074237","Code du domaine public fluvial",["cdpfnav", "domaine public fluvial et navigation"]],
    ["CTravM","LEGITEXT000006072051","Code du travail maritime",["ctravm", "travail maritime"]],
    ["CDPMM","LEGITEXT000006071188","Code disciplinaire pénal marine marchande",["cdpmm", "disciplinaire et pénal de la marine marchande"]],
    ["CPRM","LEGITEXT000006074066","Code des pensions retraite marins",["cprm", "pensions de retraite des marins"]],
    ["CDEMay","LEGITEXT000006074235","Code du domaine Etat Mayotte",["cdemay", "domaine de l'état à mayotte"]],
    ["CIMM","LEGITEXT000006070666","Code des instruments monétaires",["cimm", "instruments monétaires et médailles"]],
    ["CDA","LEGITEXT000006074232","Code de déontologie des architectes",["cda", "domaine de l'état (collectivités d'outre-mer)"]]
  ];
  var PAR_SIGLE = {}, PAR_LEGITEXT = {}, PAR_ALIAS = {};
  CODES.forEach(function (c) {
    PAR_SIGLE[c[0]] = c; PAR_LEGITEXT[c[1]] = c;
    PAR_ALIAS[normAlias(c[0])] = c;
    PAR_ALIAS[normAlias(c[2])] = c;
    c[3].forEach(function (a) { PAR_ALIAS[normAlias(a)] = c; });
  });

  /* Textes NON codifiés que sources/legi.py:98-103 sert par un sigle : ils ne
     sont pas dans la grille des codes, mais la barre doit les reconnaître. */
  var HORS_CODE_NOMMES = [
    ['CONST', 'Constitution du 4 octobre 1958', ['constitution', 'const']],
    ['LIL', 'Loi Informatique et Libertés (loi n° 78-17)', ['loi informatique et libertés', 'lil']],
    ['LO58', 'Ordonnance organique n° 58-1067', ['ordonnance 58-1067', 'lo58']],
    ['L2005-102', 'Loi handicap n° 2005-102', ['loi handicap']]
  ];
  HORS_CODE_NOMMES.forEach(function (c) {
    PAR_SIGLE[c[0]] = [c[0], '', c[1], c[2]];
    PAR_ALIAS[normAlias(c[0])] = PAR_SIGLE[c[0]];
    PAR_ALIAS[normAlias(c[1])] = PAR_SIGLE[c[0]];
    c[2].forEach(function (a) { PAR_ALIAS[normAlias(a)] = PAR_SIGLE[c[0]]; });
  });

  /* « C. civ. », « c.civ », « Code Civil » → une seule clé. Les accents sont
     conservés : « pénal » et « penal » sont tous deux indexés plus bas. */
  function normAlias(s) {
    return String(s || '').toLowerCase().replace(/[. ]/g, '').replace(/\s+/g, ' ').trim();
  }
  function sansAccent(s) {
    return String(s || '').normalize ? String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '') : String(s || '');
  }
  /* Deuxième index, sans accents : « code penal » trouve « Code pénal ». */
  var PAR_ALIAS_NA = {};
  Object.keys(PAR_ALIAS).forEach(function (k) {
    var k2 = sansAccent(k);
    if (!PAR_ALIAS_NA[k2]) PAR_ALIAS_NA[k2] = PAR_ALIAS[k];
  });
  function codeParNom(s) {
    var k = normAlias(s);
    return PAR_ALIAS[k] || PAR_ALIAS_NA[sansAccent(k)] || null;
  }

  /* Tri par SUJET du code : « Code de la santé publique » se range à « santé »,
     pas à « Code » (hub.html:414-415, repris au mot près). */
  function cleTri(nom) {
    return sansAccent(String(nom).toLowerCase())
      .replace(/^code\s+(de\s+la\s+|de\s+l'|du\s+|des\s+|de\s+|d')?/, '')
      .replace(/^(la|le|les|l')\s+/, '');
  }
  function codesTries() {
    return CODES.slice().sort(function (a, b) {
      return cleTri(a[2]).localeCompare(cleTri(b[2]), 'fr', { sensitivity: 'base' });
    });
  }

  /* ═══════════════ 2. État ═════════════════════════════════════════════ */

  var S = {
    q: '', code: '', date: '',
    results: [], srcState: {}, pager: null, seq: 0, enVol: false,
    ref: null,        /* référence reconnue par l'analyseur, avant résolution */
    article: null     /* réponse de /api/law */
  };

  /* ═══════════════ 3. Analyseur de référence ═══════════════════════════

     ⚠ MESURÉ le 13/09/2026 : l'éclaireur du serveur (/api/search&citation_only=1,
     recherche.js:306-321) ne reconnaît PAS une référence d'article de loi —
     « art. 1240 C. civ. » renvoie citation_match:false. Il ne connaît que les
     citations de DÉCISIONS. L'analyse d'une référence d'article se fait donc
     ici, côté page, exactement comme dans hub.html:874-882, puis la résolution
     passe par /api/law (article) ou /api/law/resolve (loi par son numéro). */

  /* « L. 1152-1 » → « L1152-1 » ; « 1240 » → « 1240 » ; « 1655 sexies » reste.
     C'est la forme attendue par /api/law (mesuré : CC/1240, CPC/748-6). */
  function normNum(n) {
    var s = String(n).trim().replace(/\s*\.\s*/g, '.').replace(/^([LRDAlrda])\.?\s*/, function (m, l) {
      return l.toUpperCase();
    });
    return s.replace(/\s+/g, ' ').replace(/^([LRDA])\s+(\d)/, '$1$2').trim();
  }

  var NUM = "(?:[LRDAlrda]\\.?\\s*)?\\d+(?:[-\\u2011]\\d+)*(?:\\s+(?:bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies|[A-Z]))?";

  function analyserRef(q) {
    var s = String(q || '').trim();
    if (!s) return null;

    /* (a) une loi / ordonnance / décret par son NUMÉRO : « loi n° 78-17 »,
       « loi 2005-102 du 11 février 2005 », « décret n° 2016-1480 ». */
    var mn = /\b(\d{2,4}-\d{1,6})\b/.exec(s);
    if (mn && /\b(loi|ordonnance|d[ée]cret|n[°º])\b/i.test(s) && !codeDansLaChaine(s)) {
      return { genre: 'numero', numero: mn[1], brut: s };
    }

    /* (b) référence d'article : numéro puis nom du code (« 1240 C. civ. »,
       « art. L. 1152-1 du code du travail ») */
    var t = s.toLowerCase()
      .replace(/^articles?\b\.?\s*/, '').replace(/^art\.?\s*/, '')
      .replace(/\s+du\s+/, ' ').replace(/\s+de\s+la\s+/, ' ').replace(/\s+/g, ' ').trim();
    var m = new RegExp('^(' + NUM + ')\\s+(.+)$').exec(t);
    if (m) {
      var c = codeParNom(m[2].replace(/[.,;]$/, ''));
      if (c) return { genre: 'article', code: c[0], nom: c[2], num: normNum(m[1]), brut: s };
    }
    /* (c) l'inverse : nom du code puis numéro (« CPC 748-6 », « code du
       travail L. 1152-1 »). On essaie les découpes de la plus longue à la
       plus courte pour que « code de procédure civile 748-6 » marche. */
    var mots = t.split(' ');
    for (var i = mots.length - 1; i >= 1; i--) {
      var tete = mots.slice(0, i).join(' '), queue = mots.slice(i).join(' ');
      var c2 = codeParNom(tete.replace(/[.,;]$/, ''));
      if (c2 && new RegExp('^' + NUM + '$').test(queue)) {
        return { genre: 'article', code: c2[0], nom: c2[2], num: normNum(queue), brut: s };
      }
    }
    return null;
  }
  function codeDansLaChaine(s) {
    var t = s.toLowerCase();
    return /\bcode\b/.test(t) || /\bc\.\s*(civ|p[ée]n|com|trav|cons|env|urb)\b/.test(t);
  }

  /* ═══════════════ 4. Résolution et fiche d'article ════════════════════ */

  async function resoudreArticle(code, num, date) {
    var c = J.cacheLoiGet(code, num, date || null);
    if (c) return c;
    try {
      var r = await fetch(API + '/api/law?code=' + encodeURIComponent(code) +
        '&num=' + encodeURIComponent(num) + (date ? '&date=' + encodeURIComponent(date) : ''));
      if (!r.ok) return { error: 'HTTP ' + r.status };
      var d = await r.json();
      J.cacheLoiSet(code, num, date || null, d);
      return d;
    } catch (e) { return { error: e.message || 'pas de réponse' }; }
  }

  function pastilleEtat(etat) {
    var e = String(etat || '').toUpperCase();
    /* Trois couleurs, et rien d'autre : vert en vigueur, rouge atténué
       abrogé, gris quand l'état n'est pas résolu. Un état inconnu n'est
       JAMAIS peint en vert. */
    var cls = e === 'VIGUEUR' ? 'jl-pastille--ok'
      : (e.indexOf('ABROGE') === 0 ? 'jl-pastille--morte' : 'jl-pastille--q');
    var lbl = { VIGUEUR: 'en vigueur', MODIFIE: 'modifié', ABROGE: 'abrogé',
      VIGUEUR_DIFF: 'en vigueur (différé)', ABROGE_DIFF: 'abrogation à venir',
      PERIME: 'périmé', ANNULE: 'annulé', TRANSFERE: 'transféré' }[e] || (e ? e.toLowerCase() : 'état non résolu');
    return '<span class="jl-pastille ' + cls + '" title="' +
      esc('État LEGI : ' + (e || 'non renseigné')) + '">' + esc(lbl) + '</span>';
  }

  function lienLegifranceArticle(d, code, num) {
    /* source_url est servi à 100 % par /api/law (inventaire_champs_13sept.md §7)
       et il est DATÉ : .../article_lc/LEGIARTI…/2016-10-01. On ne le reconstruit
       donc jamais nous-mêmes quand il est là. */
    if (d && d.source_url) return d.source_url;
    if (d && d.legiarti) return 'https://www.legifrance.gouv.fr/codes/article_lc/' + encodeURIComponent(d.legiarti);
    return 'https://www.legifrance.gouv.fr/search/all?query=' + encodeURIComponent('article ' + num + ' ' + code);
  }

  function rendreFiche() {
    var box = $('#fiche');
    if (!S.ref) { box.innerHTML = ''; return; }

    if (S.ref.genre === 'chargement') {
      box.innerHTML = '<div class="jl-carte" data-espace="haut"><p class="jl-muted">' +
        '<span class="jl-spin"></span> Résolution de la référence…</p></div>';
      return;
    }
    if (S.ref.genre === 'numero') return rendreFicheNumero(box);

    var d = S.article, code = S.ref.code, num = S.ref.num;
    if (!d || d.error || !d.texte) {
      /* ⛔ « introuvable » n'est pas « n'existe pas » : on le dit, et on donne
         la voie de sortie (recherche Légifrance). Même formulation que
         recherche.js:761-763. */
      box.innerHTML = '<div class="jl-honnetete" data-espace="haut"><b>Référence lue, article non résolu.</b> ' +
        'La référence <b>' + esc(S.ref.nom + ' ' + num) + '</b> a bien été reconnue, mais notre base ' +
        'ne rend pas cet article' + (d && d.error ? ' (' + esc(d.error) + ')' : '') + '. ' +
        'Ce n’est pas la preuve qu’il n’existe pas. ' +
        '<a href="' + esc(lienLegifranceArticle(null, code, num)) + '" target="_blank" rel="external noopener nofollow">' +
        'Chercher sur Légifrance ↗</a>' +
        (S.q ? ' · la recherche en plein texte ci-dessous continue.' : '') + '</div>';
      return;
    }

    var plage = d.date_debut
      ? 'Rédaction du ' + J.fmtDate(d.date_debut) +
        (d.date_fin && d.date_fin !== '2999-01-01' ? ' au ' + J.fmtDate(d.date_fin) : ', toujours applicable')
      : '';
    /* Un texte d'article arrive souvent en un seul bloc : JL.decouperTexte
       (= splitLegalBlock de search.html) lui rend ses paragraphes. */
    var paras = String(d.texte).indexOf('\n') >= 0
      ? String(d.texte).split(/\n+/).map(function (p) { return p.trim(); }).filter(Boolean)
      : J.decouperTexte(d.texte);

    box.innerHTML = '<article class="jl-fart" data-espace="haut">' +
      '<div class="jl-fart__meta">' +
        '<span class="jl-src-badge jl-src-badge--admin" title="Fonds interrogé : LEGI, codes et textes consolidés diffusés par la DILA">LEGI</span>' +
        '<span class="jl-tag jl-tag--txt">Texte</span>' +
        pastilleEtat(d.etat) +
        (plage ? '<span>' + esc(plage) + '</span>' : '<span class="jl-vide">date de rédaction -</span>') +
        (S.date ? '<span class="jl-provenance" title="Rédaction demandée à cette date.">à la date du ' +
          esc(J.fmtCourt(S.date)) + '</span>' : '') +
      '</div>' +
      '<h2 class="jl-fart__t">Article ' + esc(d.num || num) +
        (d.titre_texte ? ' <span class="jl-fart__code">' + esc(d.titre_texte) + '</span>' : '') + '</h2>' +
      (d.titre_section
        ? '<p class="jl-fart__sect" title="Emplacement de l’article dans le plan du texte (champ titre_section de LEGI).">' +
          esc(d.titre_section) + '</p>'
        : '<p class="jl-fart__sect jl-vide">section non renseignée par LEGI</p>') +
      '<div class="jl-txt">' + paras.map(function (p) {
        return '<p>' + J.lierArticles(esc(p)) + '</p>';
      }).join('') + '</div>' +
      (d.nota ? '<div class="jl-nota" data-espace="haut"><b>Nota.</b> ' + esc(d.nota) + '</div>'
              : '<p class="jl-provenance">pas de nota dans LEGI pour cette rédaction</p>') +
      '<div class="jl-fart__pied">' +
        (PAR_SIGLE[code] && PAR_SIGLE[code][1] !== undefined
          ? '<a class="jl-bouton jl-bouton--cta jl-bouton--sm" href="' +
            esc(LOI_BASE + '/' + encodeURIComponent(code) + '/' + encodeURIComponent(d.num || num)) +
            '">Page de l’article</a>' : '') +
        '<button type="button" class="jl-bouton jl-bouton--ghost jl-bouton--sm" id="artVersions">Toutes les versions</button>' +
        '<a class="jl-bouton jl-bouton--ghost jl-bouton--sm" href="' +
          esc(lienLegifranceArticle(d, code, num)) + '" target="_blank" rel="external noopener nofollow">Légifrance ↗</a>' +
        '<button type="button" class="jl-bouton jl-bouton--ghost jl-bouton--sm" id="artTxt">Télécharger .txt</button>' +
        /* Deux boutons GRIS : la carte dynamique et l'historique ne sont pas
           branchés sur l'API (web/v2/article.html ne tourne que sur CPC 748-6,
           avec des données figées). Dire « bientôt » plutôt que mener à une
           page qui montrerait un autre article que celui demandé. */
        '<button type="button" class="jl-bouton jl-bouton--sm jl-bouton--desactive" disabled aria-disabled="true" ' +
          'title="La carte de l’article n’est pas encore branchée sur l’API : la maquette ne tourne que sur un article figé.">' +
          'Carte de l’article <span class="jl-soonpill">bientôt</span></button>' +
        '<button type="button" class="jl-bouton jl-bouton--sm jl-bouton--desactive" disabled aria-disabled="true" ' +
          'title="L’historique comparé n’est pas encore branché sur l’API : la maquette ne tourne que sur un article figé.">' +
          'Historique <span class="jl-soonpill">bientôt</span></button>' +
        '<button type="button" class="jl-provenance" data-signal="' + esc(code + ' ' + num) +
          '" data-titre="' + esc('Article ' + num + ' ' + (d.titre_texte || code)) + '">signaler</button>' +
      '</div>' +
      '<div class="jl-fart__prov">LEGI · DILA' +
        (d.legiarti ? ' · <span class="jl-mono">' + esc(d.legiarti) + '</span>' : '') +
        (d.legitext ? ' · <span class="jl-mono">' + esc(d.legitext) + '</span>' : '') +
        ' · Licence Ouverte 2.0. Le texte est cité, jamais résumé.</div>' +
      '<div id="artVBox"></div>' +
      '</article>';

    var bv = $('#artVersions'); if (bv) bv.onclick = toutesLesVersions;
    var bt = $('#artTxt');
    if (bt) bt.onclick = function () {
      J.telecharger(code + '_' + (d.num || num),
        'Article ' + (d.num || num) + ' — ' + (d.titre_texte || code) + '\n' +
        (d.titre_section ? d.titre_section + '\n' : '') +
        (d.date_debut ? 'Rédaction du ' + J.fmtDate(d.date_debut) + '\n' : '') +
        (d.etat ? 'État : ' + d.etat + '\n' : '') +
        'Source : LEGI / DILA via justicelibre.org (Licence Ouverte 2.0)\n' +
        lienLegifranceArticle(d, code, num) + '\n\n' + (d.texte || '') +
        (d.nota ? '\n\nNota. ' + d.nota : '') + '\n');
    };
  }

  /* Loi / ordonnance désignée par son numéro : /api/law/resolve rend le
     LEGITEXT, le titre et le nombre d'articles (token_server.py:239-247). */
  function rendreFicheNumero(box) {
    var d = S.article;
    if (!d || d.error || !d.legitext) {
      box.innerHTML = '<div class="jl-honnetete" data-espace="haut"><b>Numéro lu, texte non résolu.</b> ' +
        'Aucune loi ni ordonnance n° <b>' + esc(S.ref.numero) + '</b> dans notre base' +
        (d && d.error ? ' (' + esc(d.error) + ')' : '') + '. Ce n’est pas la preuve qu’elle n’existe pas. ' +
        (S.q ? 'La recherche en plein texte ci-dessous cherche le numéro dans le texte des articles.' : '') +
        '</div>';
      return;
    }
    box.innerHTML = '<article class="jl-fart" data-espace="haut">' +
      '<div class="jl-fart__meta">' +
        '<span class="jl-src-badge jl-src-badge--admin" title="Fonds interrogé : LEGI / JORF, DILA">LEGI</span>' +
        '<span class="jl-tag jl-tag--txt">Texte</span>' +
        (d.date_debut ? '<span>en vigueur depuis le ' + esc(J.fmtDate(d.date_debut)) + '</span>'
                      : '<span class="jl-vide">date d’entrée en vigueur -</span>') +
      '</div>' +
      '<h2 class="jl-fart__t">' + esc(d.titre_texte || ('Texte n° ' + S.ref.numero)) + '</h2>' +
      '<p class="jl-fart__sect">' +
        (typeof d.articles_count === 'number'
          ? J.nb(d.articles_count) + ' article' + (d.articles_count > 1 ? 's' : '') + ' en base'
          : 'nombre d’articles non renseigné') + '</p>' +
      '<div class="jl-fart__pied">' +
        '<a class="jl-bouton jl-bouton--cta jl-bouton--sm" href="' +
          esc(LOI_BASE + '/' + encodeURIComponent(d.legitext) + '/1') + '">Ouvrir l’article 1<sup>er</sup></a>' +
        '<a class="jl-bouton jl-bouton--ghost jl-bouton--sm" href="' +
          esc(d.source_url || ('https://www.legifrance.gouv.fr/loda/id/' + encodeURIComponent(d.legitext))) +
          '" target="_blank" rel="external noopener nofollow">Légifrance ↗</a>' +
      '</div>' +
      '<div class="jl-fart__prov">LEGI · DILA · <span class="jl-mono">' + esc(d.legitext) + '</span>' +
        ' · Licence Ouverte 2.0. La barre ne sait pas encore viser un article ' +
        'précis d’un texte hors code : ouvrez l’article 1<sup>er</sup>, la page serveur donne les suivants.</div>' +
      '</article>';
  }

  async function toutesLesVersions() {
    var box = $('#artVBox');
    if (!box || !S.ref || S.ref.genre !== 'article') return;
    box.innerHTML = '<p class="jl-muted" data-espace="haut"><span class="jl-spin"></span> Chargement des rédactions…</p>';
    try {
      var r = await fetch(API + '/api/law/versions?code=' + encodeURIComponent(S.ref.code) +
        '&num=' + encodeURIComponent(S.ref.num));
      var d = await r.json();
      var vs = d.versions || [];
      if (!vs.length) {
        box.innerHTML = '<div class="jl-honnetete" data-espace="haut">Aucune autre rédaction de cet article ' +
          'dans LEGI. Ce n’est pas la preuve qu’il n’a jamais été modifié : c’est ce que la base contient.</div>';
        return;
      }
      box.innerHTML = '<div class="jl-surtitre" data-espace="haut">Toutes les rédactions · ' + vs.length +
        ' <span class="jl-provenance">LEGI · DILA</span></div>' +
        vs.map(function (v) {
          return '<div class="jl-loi__v"><div class="jl-muted jl-petit">' +
            esc(J.fmtCourt(v.date_debut)) + ' → ' +
            esc(v.date_fin && v.date_fin !== '2999-01-01' ? J.fmtCourt(v.date_fin) : 'toujours applicable') +
            ' ' + pastilleEtat(v.etat) +
            (v.source_url ? ' <a href="' + esc(v.source_url) + '" target="_blank" rel="external noopener nofollow">Légifrance ↗</a>' : '') +
            '</div><div>' + esc(v.texte || '') + '</div>' +
            (v.nota ? '<div class="jl-nota"><b>Nota.</b> ' + esc(v.nota) + '</div>' : '') + '</div>';
        }).join('');
    } catch (e) {
      box.innerHTML = '<div class="jl-alerte" data-espace="haut"><b>Échec :</b> ' + esc(e.message || 'pas de réponse') +
        '. Rien n’est affiché plutôt qu’une liste partielle de rédactions.</div>';
    }
  }

  /* ═══════════════ 5. Recherche en plein texte (LEGI) ══════════════════ */

  var CLE = 'LEGI · articles de loi';

  function lancer() {
    var q = $('#q').value.trim();
    /* Garde-fou double envoi (recherche.js:273-275). */
    if (S.enVol && q === S.q) return;
    S.q = q;
    syncUrl();
    if (!q) {
      S.results = []; S.srcState = {}; S.pager = null; S.ref = null; S.article = null;
      $('#fiche').innerHTML = ''; $('#srcState').innerHTML = '';
      $('#topline').innerHTML = ''; $('#avertissements').innerHTML = ''; $('#liste').innerHTML = '';
      $('#parcours').hidden = false;
      majResume();
      return;
    }
    S.enVol = true;
    $('#goBtn').disabled = true;
    chercher().then(fini, fini);
    function fini() { S.enVol = false; $('#goBtn').disabled = false; }
  }

  async function chercher() {
    var seq = ++S.seq, q = S.q;
    S.results = []; S.srcState = {}; S.article = null;
    $('#parcours').hidden = true;
    $('#avertissements').innerHTML = '';
    $('#liste').innerHTML = '<p class="jl-muted"><span class="jl-spin"></span> Recherche en cours…</p>';

    /* (1) Accès direct par référence, EN TÊTE. Il ne remplace pas la recherche
       lexicale : les deux coexistent, parce qu'une référence peut être lue
       sans que l'article soit résolu. */
    S.ref = analyserRef(q);
    if (S.ref) {
      var lue = S.ref;
      S.ref = { genre: 'chargement' };
      rendreFiche();
      var d = lue.genre === 'numero'
        ? await resoudreNumero(lue.numero)
        : await resoudreArticle(lue.code, lue.num, S.date);
      if (seq !== S.seq) return;
      S.ref = lue; S.article = d;
      rendreFiche();
    } else {
      $('#fiche').innerHTML = '';
    }

    /* (2) Plein texte LEGI. Une seule source : le pluriel des pastilles de
       recherche.js n'a pas lieu d'être, l'état unique le remplace. */
    S.pager = { q: q, seq: seq, offset: 0, total: undefined, exact: true, more: false, busy: false };
    S.srcState[CLE] = { etat: 'run' };
    renderSources();
    await interroger(0, 20);
    if (seq !== S.seq) return;
    renderResults();
    /* Relance automatique à 60 s après un DÉLAI (jamais après un refus 4xx :
       le rejouer serait voué au même refus — recherche.js:394-405). */
    if (S.srcState[CLE] && S.srcState[CLE].etat === 'delai') {
      S.srcState[CLE] = { etat: 'run', why: 'seconde tentative, 60 s' };
      renderSources(); renderResults();
      await interroger(0, 60);
      if (seq !== S.seq) return;
      renderResults();
    }
  }

  async function resoudreNumero(numero) {
    try {
      var r = await fetch(API + '/api/law/resolve?numero=' + encodeURIComponent(numero));
      var d = await r.json();
      if (!r.ok) return { error: d.error || ('HTTP ' + r.status) };
      return d;
    } catch (e) { return { error: e.message || 'pas de réponse' }; }
  }

  async function interroger(offset, timeout) {
    var P = S.pager, seq = P.seq;
    /* ?timeout=N dans l'adresse force le délai envoyé à l'API : sert à
       PROVOQUER l'état « source en délai » pour le vérifier (timeout=1). */
    var force = new URLSearchParams(location.search).get('timeout');
    var params = new URLSearchParams({ q: P.q, limit: String(PAGE), offset: String(offset),
      sources: 'legi', juridiction: 'legi', timeout: String(force || timeout || 20) });
    try {
      var r = await fetch(API + '/api/search?' + params);
      var ct = r.headers.get('content-type') || '';
      if (ct.indexOf('json') < 0) throw new Error('HTTP ' + r.status);
      var d = await r.json();
      if (seq !== S.seq) return;
      /* Refus déterministe (4xx) ≠ délai dépassé : on ne rejoue pas un refus. */
      if (r.status >= 400 && r.status < 500) {
        S.srcState[CLE] = { etat: 'refus', why: d.error || ('HTTP ' + r.status) };
        renderSources(); return;
      }
      if (d.error) { S.srcState[CLE] = { etat: 'refus', why: d.error }; renderSources(); return; }
      var muette = (d.sources_no_result || d.sources_en_echec || []).indexOf('legi') >= 0;
      var recus = (d.results || []).length;
      if (muette && !recus) {
        S.srcState[CLE] = { etat: 'delai', why: "n'a pas répondu à temps (" + (timeout || 20) + ' s)' };
      } else {
        S.srcState[CLE] = { etat: 'ok', n: recus };
      }
      var vus = {};
      S.results.forEach(function (x) { vus[x.id] = 1; });
      (d.results || []).forEach(function (x) { if (!vus[x.id]) { vus[x.id] = 1; S.results.push(x); } });
      if (typeof d.total === 'number' && (offset === 0 || d.total > 0)) {
        P.total = d.total; P.exact = d.total_exact !== false;
      }
      P.offset = offset + PAGE;
      P.more = recus > 0 && (P.total !== undefined ? P.offset < P.total : recus >= PAGE);
    } catch (e) {
      if (seq !== S.seq) return;
      S.srcState[CLE] = { etat: 'delai', why: e.message || 'pas de réponse' };
    }
    renderSources(); renderResults();
  }

  async function chargerSuite() {
    var P = S.pager;
    if (!P || P.busy || !P.more) return;
    P.busy = true; renderResults();
    S.srcState[CLE] = { etat: 'run' }; renderSources();
    await interroger(P.offset, 20);
    P.busy = false; renderResults();
  }

  /* ═══════════════ 6. Pastille de source ═══════════════════════════════ */

  function renderSources() {
    var el = $('#srcState'), ks = Object.keys(S.srcState);
    if (!ks.length) { el.innerHTML = ''; return; }
    el.innerHTML = ks.map(function (k) {
      var st = S.srcState[k];
      var m = {
        run: ['jl-pastille--loader', st.why || 'interrogation en cours'],
        ok: ['jl-pastille--ok', 'a répondu' + (st.n != null ? ' · ' + st.n + ' sur cette page' : '')],
        delai: ['jl-pastille--morte', st.why || "n'a pas répondu à temps"],
        refus: ['jl-pastille--q', 'refus du serveur : ' + (st.why || '')]
      }[st.etat] || ['jl-pastille--q', 'état inconnu'];
      var suffixe = st.etat === 'delai' ? ' · délai' : st.etat === 'refus' ? ' · refus' : '';
      return '<span class="jl-pastille ' + m[0] + '" title="' + esc(k + ' : ' + m[1]) + '">' +
        esc(k) + esc(suffixe) + '</span>';
    }).join('');
  }

  /* ═══════════════ 7. Résultats ════════════════════════════════════════ */

  /* ⚠ MESURÉ le 13/09/2026 : /api/search IGNORE le paramètre `code`
     (search_api.py:652-665 `_dispatch_legi` ne le transmet pas à l'entrepôt,
     alors que sources/warehouse.py:243-265 `search_fond` l'accepte).
     Vérifié en direct : `&code=CT` sur « harcèlement » rend un décret.
     Le filtre par code ne peut donc porter que sur les résultats DÉJÀ chargés,
     et la page le dit là où c'est visible plutôt que de laisser croire à un
     filtrage du fonds. */
  function filtres() {
    if (!S.code) return S.results;
    var leg = PAR_SIGLE[S.code] ? PAR_SIGLE[S.code][1] : '';
    return S.results.filter(function (r) { return r.legitext === leg; });
  }

  function renderResults() {
    var liste = $('#liste'), tl = $('#topline'), P = S.pager || {};
    var rows = filtres(), tot = S.results.length;

    var av = [];
    if (S.srcState[CLE] && S.srcState[CLE].etat === 'refus') {
      av.push('<div class="jl-alerte jl-alerte--icone" data-espace="haut"><b>⚠</b><div><b>' + esc(CLE) +
        '</b> a refusé la requête : ' + esc(S.srcState[CLE].why || '') +
        '. Ce n’est pas un délai dépassé : rejouer la même requête donnerait le même refus.</div></div>');
    }
    var muette = S.srcState[CLE] && S.srcState[CLE].etat === 'delai';
    if (muette && rows.length) {
      av.push('<div class="jl-honnetete" data-espace="haut"><b>Recherche incomplète.</b> Le fonds LEGI ' +
        'n’a pas répondu : les articles ci-dessous ne couvrent pas le fonds. ' +
        '<button type="button" class="jl-bouton jl-bouton--ghost jl-bouton--sm" data-relancer>Relancer</button></div>');
    }
    $('#avertissements').innerHTML = av.join('');
    $$('#avertissements [data-relancer]').forEach(function (b) { b.onclick = lancer; });

    tl.innerHTML = S.q ? '<div class="jl-topline">' +
      '<span class="jl-serif jl-compte">' + J.nb(rows.length) +
      (rows.length !== tot ? ' <span class="jl-muted jl-petit">sur ' + J.nb(tot) + ' chargés</span>'
        : (rows.length === 1 ? ' article chargé' : ' articles chargés')) +
      (P.total !== undefined && P.total > tot
        ? ' <span class="jl-muted jl-petit">sur ' + J.nb(P.total) + (P.exact ? '' : ' environ') +
          ' existants</span>' : '') + '</span>' +
      '<span class="jl-muted jl-petit">' + (S.ref && S.ref.genre === 'article'
        ? 'mode <b class="jl-teal">référence</b> · l’article demandé est en tête, la liste reste lexicale'
        : 'mode <b class="jl-teal">lexical</b> · tous les mots exigés dans le texte de l’article') +
      '</span></div>' : '';

    majResume();
    if (!S.q) { liste.innerHTML = ''; return; }

    /* ⛔ Le cœur de la règle : trois « vides » distincts, jamais confondus. */
    if (!rows.length) {
      if (S.srcState[CLE] && S.srcState[CLE].etat === 'run') {
        liste.innerHTML = '<p class="jl-muted" data-espace="haut"><span class="jl-spin"></span> Recherche en cours…</p>';
      } else if (muette) {
        liste.innerHTML = '<div class="jl-honnetete" data-espace="haut"><b>Recherche incomplète.</b> ' +
          'Le fonds LEGI n’a pas répondu à temps : ce « rien » ne veut pas dire qu’il n’y a rien. ' +
          'Aucune conclusion ne peut être tirée de cette absence. ' +
          '<button type="button" class="jl-bouton jl-bouton--ghost jl-bouton--sm" data-relancer>Relancer</button></div>';
        $$('#liste [data-relancer]').forEach(function (b) { b.onclick = lancer; });
      } else if (S.srcState[CLE] && S.srcState[CLE].etat === 'refus') {
        liste.innerHTML = '<p class="jl-muted" data-espace="haut">La source a refusé la requête (voir ci-dessus).</p>';
      } else if (S.code && tot) {
        liste.innerHTML = '<div class="jl-honnetete" data-espace="haut">Aucun des <b>' + J.nb(tot) +
          '</b> articles chargés n’appartient au <b>' + esc(PAR_SIGLE[S.code] ? PAR_SIGLE[S.code][2] : S.code) +
          '</b>. Le filtre par code ne porte que sur les articles déjà chargés : l’API ne sait pas ' +
          'encore restreindre une recherche à un code. Chargez la suite, ou retirez le filtre.</div>';
      } else if (S.ref && S.article && !S.article.error) {
        /* Cas fréquent et non inquiétant : la requête EST une référence, donc
           ses mots (« art. », « C. civ. ») ne figurent pas dans le texte des
           articles. L'article demandé est en tête ; la liste est vide pour une
           raison connue, et on la nomme au lieu de laisser un « rien ». */
        liste.innerHTML = '<p class="jl-muted" data-espace="haut">Rien en plus. ' +
          'La requête est une référence : l’article demandé est affiché ci-dessus. ' +
          'La source a répondu, et aucun article ne contient ces mots dans son texte, ' +
          'ce qui est normal pour une abréviation de code.</p>';
      } else {
        liste.innerHTML = '<p class="jl-muted" data-espace="haut">Aucun article. ' +
          'La source a répondu : il n’y a rien pour cette requête dans le plein texte des articles. ' +
          'Essayez des mots plus larges, ou une référence d’article.</p>';
      }
      return;
    }

    liste.innerHTML = (S.code ? noteFiltreCode() : '') +
      rows.map(carteArticle).join('') + boutonSuite();
    var mb = $('#plusBtn'); if (mb) mb.onclick = chargerSuite;
  }

  function noteFiltreCode() {
    return '<div class="jl-honnetete" data-espace="haut"><b>Filtre local.</b> ' +
      'Le filtre « ' + esc(PAR_SIGLE[S.code] ? PAR_SIGLE[S.code][2] : S.code) + ' » est appliqué ' +
      '<b>aux articles déjà chargés</b>, pas au fonds : mesuré le 13 septembre 2026, ' +
      '<span class="jl-mono">/api/search</span> ignore le paramètre <span class="jl-mono">code</span>. ' +
      'Ne tirez donc aucune statistique de ce compte. Pour un article précis de ce code, ' +
      'écrivez sa référence dans la barre.</div>';
  }

  function carteArticle(r) {
    var c = PAR_LEGITEXT[r.legitext] || null;
    var num = r.numero || '';
    /* Lecture : la page serveur /loi/<sigle>/<num> quand le sigle est
       résolvable ; sinon Légifrance, en le DISANT. */
    var href = c ? LOI_BASE + '/' + encodeURIComponent(c[0]) + '/' + encodeURIComponent(num) : '';
    var extLegi = r.source_url ||
      (r.id ? 'https://www.legifrance.gouv.fr/loda/article_lc/' + encodeURIComponent(r.id) : '');
    var titre = String(r.title || '(sans titre)');
    var brut = String(r.extract || '').replace(/[ \t]*\n[ \t\n_]*/g, ' · ')
      .replace(/\s{2,}/g, ' ').replace(/^(…|\.\.\.)?\s*·\s*/, '…').trim();
    var sum = J.clipExtract(brut, 420);
    var html = sum ? J.lierArticles(J.surlignerExtrait(sum, S.q, 420)) : '';

    return '<article class="jl-resultat">' +
      '<div class="jl-resultat__meta">' +
        '<span class="jl-src-badge jl-src-badge--admin" title="Fonds interrogé : LEGI (DILA)">LEGI</span>' +
        '<span class="jl-tag jl-tag--txt">Texte</span>' +
        pastilleEtat(r.etat) +
        (r.date ? '<span title="Date de début de cette rédaction (champ date de LEGI).">' +
          esc(J.fmtDate(r.date)) + '</span>' : '<span class="jl-vide">date -</span>') +
      '</div>' +
      '<h3 class="jl-resultat__t">' +
        (href ? '<a href="' + esc(href) + '">' + esc(titre) + '</a>'
              : (extLegi ? '<a href="' + esc(extLegi) + '" target="_blank" rel="external noopener nofollow">' +
                  esc(titre) + ' ↗</a>' : esc(titre))) +
      '</h3>' +
      (html ? '<p class="jl-resultat__x">' + html + '</p>'
            : '<p class="jl-resultat__x"><span class="jl-warnp">pas d’extrait renvoyé</span></p>') +
      '<div class="jl-resultat__ref">' +
        (num ? '<span>art. ' + esc(num) + '</span>' : '<span class="jl-vide">n° -</span>') +
        '<span>·</span><span class="jl-muted">' + esc(r.juridiction || 'texte non nommé') + '</span>' +
        '<span>·</span><span class="jl-provenance" title="Fonds LEGI, diffusé par la DILA sous Licence Ouverte 2.0.">LEGI · DILA</span>' +
        (c ? '' : '<span>·</span><span class="jl-provenance" title="' +
          esc('Ce texte (' + (r.legitext || 'identifiant absent') + ') n’a pas de sigle court dans notre table : ' +
              'pas de page /loi/<code>/<num>. Le lien va directement à Légifrance.') +
          '">pas de page interne · lien Légifrance</span>') +
        (extLegi && href ? '<span>·</span><a href="' + esc(extLegi) +
          '" target="_blank" rel="external noopener nofollow">Légifrance ↗</a>' : '') +
        '<span>·</span><button type="button" class="jl-provenance" data-signal="' + esc(r.id || '') +
          '" data-titre="' + esc(titre) + '" title="Signaler un problème sur cet article">signaler</button>' +
      '</div></article>';
  }

  function boutonSuite() {
    var P = S.pager;
    if (!P || !P.more) return '';
    return '<div class="jl-plus"><button type="button" class="jl-bouton jl-bouton--cta" id="plusBtn"' +
      (P.busy ? ' disabled' : '') + '>' + (P.busy ? 'Chargement…' : 'Charger la suite') + '</button>' +
      '<div class="jl-plus__detail">LEGI : ' + J.nb(P.offset) +
      (P.total !== undefined ? ' / ' + J.nb(P.total) + (P.exact ? '' : ' env.') : '') + '</div></div>';
  }

  /* ═══════════════ 8. Les codes, en colonnes ═══════════════════════════ */

  function renderCodes() {
    var f = normAlias($('#codeFiltre') ? $('#codeFiltre').value : '');
    var fna = sansAccent(f);
    var liste = codesTries().filter(function (c) {
      if (!f) return true;
      var foin = sansAccent(normAlias(c[0] + ' ' + c[2] + ' ' + c[3].join(' ')));
      return foin.indexOf(fna) >= 0;
    });
    $('#codesSub').textContent = CODES.length + ' codes consolidés servis · LEGI · DILA · ' +
      'un clic filtre la recherche, un clic sur l’abréviation prépare une référence';
    $('#codeCount').textContent = liste.length === CODES.length
      ? CODES.length + ' codes' : liste.length + ' sur ' + CODES.length;
    if (!liste.length) {
      $('#codesGrid').innerHTML = '<p class="jl-empty">Aucun code ne porte ce mot. ' +
        'Les 75 codes sont ceux que sert l’entrepôt, pas tous ceux qui existent.</p>';
      return;
    }
    $('#codesGrid').innerHTML = liste.map(function (c) {
      var on = S.code === c[0];
      return '<div class="jl-code' + (on ? ' is-on' : '') + '">' +
        '<button type="button" class="jl-code__n" data-code="' + esc(c[0]) + '" ' +
          'title="' + esc('Filtrer la recherche sur : ' + c[2]) + '">' + esc(c[2]) + '</button>' +
        '<button type="button" class="jl-code__s" data-ref="' + esc(c[0]) + '" ' +
          'title="' + esc('Écrire une référence : art. … ' + c[0]) + '">' + esc(abrev(c)) + '</button>' +
        '</div>';
    }).join('');
    $$('#codesGrid [data-code]').forEach(function (b) {
      b.onclick = function () {
        S.code = (S.code === b.dataset.code) ? '' : b.dataset.code;
        syncUrl(); renderCodes(); majResume();
        if (S.q) renderResults(); else preparerReference(b.dataset.code);
      };
    });
    $$('#codesGrid [data-ref]').forEach(function (b) {
      b.onclick = function () { preparerReference(b.dataset.ref); };
    });
  }

  /* Abréviation affichée : la plus courte qui ne soit pas le nom complet
     (hub.html:575, repris). Le sigle sert de repli. */
  function abrev(c) {
    var nom = c[2].toLowerCase();
    var a = c[3].filter(function (x) { return x.toLowerCase() !== nom; })
      .sort(function (x, y) { return x.length - y.length; });
    return a[0] || c[0];
  }

  /* Un code cliqué prépare la référence dans la barre, curseur entre « art. »
     et le sigle : le geste de hub.html:840, transposé. */
  function preparerReference(sigle) {
    var c = PAR_SIGLE[sigle]; if (!c) return;
    var i = $('#q');
    i.value = 'art.  ' + abrev(c);
    i.focus();
    try { i.setSelectionRange(5, 5); } catch (e) {}
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  /* ═══════════════ 9. Textes hors code (ministère › nature › année) ════
     Données : web/hub_horscode.json, extrait réel de jorf_textes (JO 1990→2026),
     24 ministères. Repris de hub.html:462-538, sans les styles du prototype. */

  var NATLABEL = { LOI: 'Lois', ORDONNANCE: 'Ordonnances', DECRET: 'Décrets', ARRETE: 'Arrêtés' };
  var HC = null, hcSel = { min: '', nat: 'LOI', an: '' };

  function nomMin(s) {
    var t = String(s || '').trim();
    if (t === t.toUpperCase()) t = t.toLowerCase();
    t = t.replace(/^minist[èe]re (de la |de l'|du |des |de |d')?/i, '');
    return t.charAt(0).toUpperCase() + t.slice(1);
  }
  /* « LOI n° 2026-650 du 23 juillet 2026 relative au renforcement… (1) »
     → meta « Loi n° 2026-650 · 23 juillet 2026 », sujet « relative au… ».
     ⛔ Ce n'est pas un résumé : c'est le titre officiel, coupé à sa charnière. */
  function titreParts(titre, date) {
    var t = String(titre || '').replace(/\s*\(\d+\)\s*$/, '').trim();
    var m = t.match(/^(LOI(?: organique| constitutionnelle)?|ORDONNANCE|D[ÉE]CRET|ARR[ÊE]T[ÉE])\s+(n[°º]\s*[\w.-]+)?\s*(?:du|en date du)\s+(\d{1,2}(?:er)?\s+\S+\s+\d{4})\s*(.*)$/i);
    if (!m) return { meta: date ? J.fmtDate(date) : '', sujet: t };
    var nature = m[1].charAt(0).toUpperCase() + m[1].slice(1).toLowerCase();
    var num = (m[2] || '').replace(/\s+/g, ' ');
    return { meta: nature + (num ? ' ' + num : '') + ' · ' + m[3], sujet: (m[4] || '').trim() || t };
  }

  async function initHorsCode() {
    var box = $('#horsCode'); if (!box) return;
    if (!HC) {
      try { HC = await (await fetch('/hub_horscode.json')).json(); }
      catch (e) {
        box.innerHTML = '<div class="jl-honnetete">L’échantillon des textes hors code ' +
          '(<span class="jl-mono">hub_horscode.json</span>) n’a pas répondu. Rien n’est affiché plutôt ' +
          'qu’une liste partielle qui ferait croire à un état du Journal officiel.</div>';
        return;
      }
    }
    if (!hcSel.min) hcSel.min = HC.ministeres[0].nor;
    renderHorsCode();
  }

  function renderHorsCode() {
    var box = $('#horsCode'); if (!box || !HC) return;
    var m = HC.ministeres.filter(function (x) { return x.nor === hcSel.min; })[0] || HC.ministeres[0];
    var nats = Object.keys(m.natures).filter(function (n) { return NATLABEL[n]; });
    if (nats.indexOf(hcSel.nat) < 0) hcSel.nat = nats[0];
    var ans = Object.keys(m.natures[hcSel.nat] || {}).sort().reverse();
    if (ans.indexOf(hcSel.an) < 0) hcSel.an = ans[0] || '';
    var titres = HC.titres[m.nor + '|' + hcSel.nat + '|' + hcSel.an];
    var nAn = (m.natures[hcSel.nat] || {})[hcSel.an] || 0;

    var bloc = function (titre, items) {
      return '<div class="jl-hcfam"><div class="jl-fam__h">' + esc(titre) + '</div>' +
        '<div class="jl-hcscroll">' + items + '</div></div>';
    };
    box.innerHTML = '<div class="jl-hc">' +
      bloc('Ministère', HC.ministeres.map(function (x) {
        return '<button type="button" class="jl-fch' + (x.nor === m.nor ? ' is-on' : '') +
          '" data-min="' + esc(x.nor) + '" title="' + esc(x.nom) + '"><i></i><span>' +
          esc(nomMin(x.nom)) + '</span><span class="jl-fch__n">' + J.fmtN(x.total) + '</span></button>';
      }).join('')) +
      bloc('Nature', nats.map(function (n) {
        var t = Object.keys(m.natures[n]).reduce(function (a, k) { return a + m.natures[n][k]; }, 0);
        return '<button type="button" class="jl-fch' + (n === hcSel.nat ? ' is-on' : '') +
          '" data-nat="' + esc(n) + '"><i></i><span>' + esc(NATLABEL[n]) +
          '</span><span class="jl-fch__n">' + J.fmtN(t) + '</span></button>';
      }).join('')) +
      bloc('Année', ans.map(function (a) {
        return '<button type="button" class="jl-fch' + (a === hcSel.an ? ' is-on' : '') +
          '" data-an="' + esc(a) + '"><i></i><span>' + esc(a) + '</span><span class="jl-fch__n">' +
          J.nb(m.natures[hcSel.nat][a]) + '</span></button>';
      }).join('')) +
      '</div>' +
      '<div class="jl-fil" data-espace="haut">' + esc(m.nom) + ' <span>›</span> ' +
        esc(NATLABEL[hcSel.nat]) + ' <span>›</span> ' + esc(hcSel.an) +
        ' <span class="jl-muted jl-petit">· ' + J.nb(nAn) + ' texte' + (nAn > 1 ? 's' : '') + '</span>' +
        ' <span class="jl-provenance" title="JORF, diffusé par la DILA. Comptes mesurés sur jorf_textes (JO 1990 → 2026).">JORF · DILA</span></div>' +
      (titres && titres.length
        ? titres.map(function (t) {
            var p = titreParts(t.titre, t.date);
            return '<a class="jl-lt jl-lt--ligne" href="' + esc(LOI_BASE + '/' + encodeURIComponent(t.id) + '/1') + '">' +
              '<div class="jl-lt__meta">' + esc(p.meta) + '</div>' +
              '<div class="jl-lt__t">' + esc(p.sujet) + '</div></a>';
          }).join('') +
          (nAn > titres.length
            ? '<div class="jl-honnetete" data-espace="haut">Prototype : ' + titres.length +
              ' titres embarqués sur les ' + J.nb(nAn) + ' de ce rayon. Les autres ne sont pas cachés, ' +
              'ils ne sont pas dans l’échantillon ; la version servie interrogera l’entrepôt.</div>'
            : '')
        : '<div class="jl-honnetete" data-espace="haut">Prototype : les titres ne sont embarqués que pour ' +
          'les 10 premiers ministères et les 3 dernières années. Ce rayon compte ' + J.nb(nAn) +
          ' textes, dont aucun n’est listé ici. Ce vide est celui de l’échantillon, pas du Journal officiel.</div>');

    $$('#horsCode [data-min]').forEach(function (b) { b.onclick = function () { hcSel.min = b.dataset.min; renderHorsCode(); }; });
    $$('#horsCode [data-nat]').forEach(function (b) { b.onclick = function () { hcSel.nat = b.dataset.nat; renderHorsCode(); }; });
    $$('#horsCode [data-an]').forEach(function (b) { b.onclick = function () { hcSel.an = b.dataset.an; renderHorsCode(); }; });
  }

  /* ═══════════════ 10. URL partageable, résumé, impression ═════════════ */

  function syncUrl() {
    var p = new URLSearchParams();
    if (S.q) p.set('q', S.q);
    if (S.code) p.set('code', S.code);
    if (S.date) p.set('date', S.date);
    var force = new URLSearchParams(location.search).get('timeout');
    if (force) p.set('timeout', force);
    try { history.replaceState(null, '', location.pathname + (p.toString() ? '?' + p : '')); } catch (e) {}
  }

  function lireUrl() {
    var p = new URLSearchParams(location.search);
    S.q = p.get('q') || '';
    S.code = PAR_SIGLE[p.get('code') || ''] ? p.get('code') : '';
    S.date = p.get('date') || '';
    $('#q').value = S.q;
  }

  function majResume() {
    var el = $('#advSum');
    el.innerHTML = S.code
      ? '<button type="button" class="jl-filtre is-on" data-rm-code>' +
        esc(PAR_SIGLE[S.code] ? PAR_SIGLE[S.code][2] : S.code) + ' ✕</button>' : '';
    var b = el.querySelector('[data-rm-code]');
    if (b) b.onclick = function () { S.code = ''; syncUrl(); renderCodes(); majResume(); renderResults(); };
    majRecapImpression();
  }

  function majRecapImpression() {
    $('#recapImpression').innerHTML =
      '<b>justicelibre.org — textes</b><br>Requête : ' + (S.q ? '« ' + esc(S.q) + ' »' : '(vide)') +
      '<br>Code : ' + esc(S.code ? (PAR_SIGLE[S.code] ? PAR_SIGLE[S.code][2] : S.code) : 'aucun') +
      '<br>Source : LEGI / DILA, Licence Ouverte 2.0' +
      '<br>Adresse : ' + esc(location.href);
  }

  /* ═══════════════ 11. Démarrage ═══════════════════════════════════════ */

  function demarrer() {
    J = window.JL; $ = J.$; $$ = J.$$; esc = J.esc;

    $('#hint').innerHTML = 'Ça marche : ' + [
      'art. 1240 C. civ.', 'L. 1152-1 du code du travail', 'CPC 748-6',
      'loi n° 78-17', 'responsabilité'
    ].map(function (x) {
      return '<span class="jl-kb" data-q="' + esc(x) + '" role="button" tabindex="0">' + esc(x) + '</span>';
    }).join(' · ');
    $$('#hint .jl-kb').forEach(function (k) {
      k.onclick = function () { $('#q').value = k.dataset.q; lancer(); };
      k.onkeydown = function (e) { if (J.estEntree(e)) { e.preventDefault(); k.click(); } };
    });

    lireUrl();
    renderCodes();
    initHorsCode();
    majResume();

    $('#sform').addEventListener('submit', function (e) { e.preventDefault(); lancer(); });
    /* Entrée : vue morte au clavier le 8 septembre 2026, d'où JL.estEntree. */
    $('#q').addEventListener('keydown', function (e) { if (J.estEntree(e)) { e.preventDefault(); lancer(); } });
    $('#codeFiltre').addEventListener('input', renderCodes);

    document.addEventListener('click', function (e) {
      var sg = e.target.closest && e.target.closest('[data-signal]');
      if (!sg) return;
      e.preventDefault();
      $('#signalGh').href = J.urlSignalement({ id: sg.dataset.signal, titre: sg.dataset.titre, url: location.href });
      $('#signalModale').hidden = false;
    });
    $('#signalX').onclick = function () { $('#signalModale').hidden = true; };
    $('#signalModale').addEventListener('click', function (e) {
      if (e.target === $('#signalModale')) $('#signalModale').hidden = true;
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') $('#signalModale').hidden = true;
    });

    /* Le navigateur nomme le PDF avec le <title> : on y met la requête. */
    var titreSauve = null;
    window.addEventListener('beforeprint', function () {
      majRecapImpression();
      if (!S.q) return;
      titreSauve = document.title;
      document.title = ('Textes « ' + S.q + ' » · justicelibre.org').slice(0, 120);
    });
    window.addEventListener('afterprint', function () {
      if (titreSauve !== null) { document.title = titreSauve; titreSauve = null; }
    });

    if (S.q) lancer(); else $('#parcours').hidden = false;
  }

  if (window.JL) demarrer();
  else window.addEventListener('DOMContentLoaded', function () {
    if (window.JL) demarrer();
    else setTimeout(demarrer, 0);
  });
})();
