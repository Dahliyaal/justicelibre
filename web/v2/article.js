/**
 * article.js — modèle de domaine de la CARTE D'UN ARTICLE et de son HISTORIQUE.
 *
 * Partagé par web/v2/article.html (page « maintenant ») et
 * web/v2/historique.html (vues Couloirs et Poupées russes).
 *
 * Porté depuis web/maquettes/carte-748.html, histo-02.html et histo-05.html.
 * Ne redéfinit AUCUN helper déjà présent dans /jl.js : esc, fmtDate, fmtCourt,
 * parseFr, $, $$, pastille, plur, copy… sont pris sur window.JL.
 *
 * DEUX DIVERGENCES TRANCHÉES (rapport normaliseur_13sept.md §4) :
 *   lifeAt : la version d'histo-02.html:308-313 gagne — un texte `MODIFIE`
 *            devient {k:'q', label:'réécrit le …'} et non « abrogé le … ».
 *   minus  : la version d'histo-02.html:314 gagne — « l'arrêté », « le décret »
 *            (avec l'article défini), et non « arrêté » nu.
 *
 * API : window.ART = {loadModel, loadHisto, + helpers de domaine}.
 */
(function (global) {
  'use strict';

  var J = global.JL;
  var esc = J.esc, fmtDate = J.fmtDate, fmtCourt = J.fmtCourt;

  var DATA = '../hub_paysage_748.json';
  var CITE = '../hub_cite_748.json';

  /* ═══════════════ Vocabulaire de domaine ═══════════════════════════════ */

  var NATLABEL = { DECRET: 'décret', ARRETE: 'arrêté', CODE: 'code', LOI: 'loi',
    ORDONNANCE: 'ordonnance', DIRECTIVE_EURO: 'directive UE' };

  var HOWTIP = {
    'visa': 'Relié par ses visas : le texte commence par « Vu le code de procédure civile, notamment son article 748-6 ». C’est cette mention en tête qui permet de le rattacher à l’article.',
    'lien LEGI': 'Lien posé par Légifrance dans les données LEGI (créé par, modifié par, cité par).',
    'succession': 'Déduit d’un lien « modifie » ou « abroge » entre deux arrêtés dans LEGI.'
  };

  var SRC = { dila: 'Judilibre · DILA', jade: 'JADE · Conseil d’État',
    cedh: 'HUDOC · Cour EDH', cjue: 'CURIA · CJUE' };
  var FAMLABEL = { jud: 'judiciaire', adm: 'administratif', eu: 'européen' };

  /* citation = lien : les identifiants LEGI d'abord, le texte ensuite. */
  var CODE_SIGLE = [
    ['code de procédure civile', 'CPC'], ['code de procédure pénale', 'CPP'],
    ['code de justice administrative', 'CJA'], ['code civil', 'CC'],
    ['code pénal', 'CP'], ['code de la santé publique', 'CSP'],
    ['code du travail', 'CT'], ['code de commerce', 'CCom'],
    ['code de l’organisation judiciaire', 'COJ'], ["code de l'organisation judiciaire", 'COJ'],
    ['code des relations entre le public et l’administration', 'CRPA']
  ];

  /* ═══════════════ Helpers de domaine ═══════════════════════════════════ */

  function legifrance(id, nature) {
    id = id || '';
    if (id.indexOf('JORFTEXT') === 0) return 'https://www.legifrance.gouv.fr/jorf/id/' + id;
    if (id.indexOf('LEGIARTI') === 0) {
      return (nature === 'CODE' ? 'https://www.legifrance.gouv.fr/codes/article_lc/'
                                : 'https://www.legifrance.gouv.fr/loda/article_lc/') + id;
    }
    // Un CODE vit sous /codes/, pas sous /loda/ (bogue hérité de carte-748.html:287 ;
    // « citation = lien » exige que le lien tombe au bon endroit, 13 sept. 2026).
    if (id.indexOf('LEGITEXT') === 0) {
      return (nature === 'CODE' ? 'https://www.legifrance.gouv.fr/codes/id/'
                                : 'https://www.legifrance.gouv.fr/loda/id/') + id;
    }
    return 'https://www.legifrance.gouv.fr/';
  }

  /* TRANCHÉ : version histo-02 (cas MODIFIE). */
  function lifeAt(t, at) {
    if (!t) return { k: 'q', label: 'non résolu', why: 'identifiant absent de l’entrepôt' };
    var d0 = t.date_debut || '0000', d1 = t.date_fin || '2999';
    if (d0 > at) return { k: 'fut', label: 'entre en vigueur le ' + fmtCourt(d0), why: 'postérieur à la date lue' };
    if (d1 <= at) {
      var e = t.etat || '';
      if (e.indexOf('MODIFIE') === 0) {
        return { k: 'q', label: 'réécrit le ' + fmtCourt(d1),
          why: 'Légifrance a ouvert un nouvel identifiant pour ce texte à cette date (même NOR) : la suite est sous l’autre entrée' };
      }
      return { k: 'ab', label: (e.indexOf('PERIM') === 0 ? 'périmé' : 'abrogé') + ' le ' + fmtCourt(d1),
        why: 'ne joue plus à la date lue' };
    }
    return { k: 'ok', label: 'en vigueur', why: 'depuis le ' + fmtDate(d0) };
  }

  /* TRANCHÉ : version histo-02 — l'article défini est inclus. */
  function minus(s) {
    return String(s || '').replace(/^Arrêté/, 'l’arrêté').replace(/^Décret/, 'le décret');
  }

  function clean(s) { return String(s || '').replace(/\s+/g, ' ').trim(); }
  function titreArr(t) {
    return (t.titre_long && t.titre_long.length > (t.titre || '').length + 3)
      ? t.titre_long : (t.titre || t.legitext);
  }
  /* Accordeur de pluriel de histo-02.html:317 — jl.js réserve `nb` au
     formateur de nombres et `plur` à l'accord SANS forme « aucun ». */
  function acc(n, un, plus) {
    return n === 0 ? 'aucun' + (un.slice(-1) === 'e' ? 'e' : '') + ' ' + un
      : n === 1 ? '1 ' + un : n + ' ' + (plus || un + 's');
  }

  function words(t) {
    return (t || '').toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, ' ').split(/\s+/)
      .filter(function (w) { return w.length > 2; });
  }
  function jaccard(a, b) {
    var A = new Set(words(a)), B = new Set(words(b));
    if (!A.size && !B.size) return 1;
    var i = 0; A.forEach(function (w) { if (B.has(w)) i++; });
    return i / (A.size + B.size - i);
  }

  /* Diff mot à mot (hub.html → histo-02.html:323-331) : ajouts verts, retraits rouges. */
  function diffWords(a, b) {
    var A = a.split(/(\s+)/), B = b.split(/(\s+)/);
    var n = A.length, m = B.length;
    var dp = []; for (var k = 0; k <= n; k++) dp.push(new Uint16Array(m + 1));
    for (var i0 = n - 1; i0 >= 0; i0--) for (var j0 = m - 1; j0 >= 0; j0--) {
      dp[i0][j0] = A[i0] === B[j0] ? dp[i0 + 1][j0 + 1] + 1 : Math.max(dp[i0 + 1][j0], dp[i0][j0 + 1]);
    }
    var i = 0, j = 0, out = '';
    while (i < n && j < m) {
      if (A[i] === B[j]) { out += esc(A[i]); i++; j++; }
      else if (dp[i + 1][j] >= dp[i][j + 1]) { out += '<del>' + esc(A[i]) + '</del>'; i++; }
      else { out += '<ins>' + esc(B[j]) + '</ins>'; j++; }
    }
    while (i < n) out += '<del>' + esc(A[i++]) + '</del>';
    while (j < m) out += '<ins>' + esc(B[j++]) + '</ins>';
    return out;
  }

  /* ═══════════════ Rendu commun ═════════════════════════════════════════ */

  /* Les quatre états de `lifeAt` sur les quatre pastilles de jl.css. */
  var PK = { ok: 'ok', ab: 'morte', q: 'q', fut: 'future' };
  function pill(st) { return J.pastille(PK[st.k] || 'q', st.label, st.why || ''); }
  function howHTML(h) { return J.noteProvenance(h, HOWTIP[h] || 'provenance du lien'); }

  /* citation = lien, par les identifiants LEGI d'abord : le numéro ne sert
     qu'à trouver la position dans la phrase, l'identifiant fait le lien. */
  function linkArtsLEGI(html, liens) {
    var cites = (liens || []).filter(function (l) {
      return l.typelien === 'CITATION' && l.sens === 'source' && l.num &&
        (l.id || '').indexOf('LEGIARTI') === 0;
    });
    cites.forEach(function (l) {
      var num = String(l.num).replace(/\s+/g, '');
      var re = new RegExp('(articles?|art\\.)(\\s+(?:[LRD]\\.?\\s?)?)(' +
        num.replace(/[.*+?^${}()|[\]\\-]/g, '\\$&') + ')(?![\\d-])', 'gi');
      var code = (l.libelle || '').match(/^(.*?) - art\./);
      var titre = code ? code[1] : '';
      html = html.replace(re, function (m, mot, sp, n) {
        return mot + sp + '<a class="jl-artlink" href="../hub.html#/article/' +
          encodeURIComponent(l.cidtexte || '') + '/' + encodeURIComponent(num) +
          '" data-legiarti="' + esc(l.id) + '" title="' + esc(titre) + ' · ' + esc(l.id) +
          ' · lien LEGI">' + n + '</a>';
      });
    });
    return html;
  }
  /* Repli textuel quand aucun identifiant LEGI ne couvre la mention. */
  function linkArts(html, codeIci) {
    return html.replace(/(articles?|art\.)\s+(?!<a )((?:[LRD]\.?\s?)?\d[\d\-]*(?:\s*(?:,|et)\s*(?:[LRD]\.?\s?)?\d[\d\-]*)*)(\s+(?:du|de ce|du même|du présent)\s+(?:code(?: [^.,;:]{0,60})?|même code|présent code))?/gi,
      function (m, mot, nums, suite) {
        var code = codeIci;
        if (suite && /\bdu\s+code\b/i.test(suite) && !/même|présent/i.test(suite)) {
          var s = suite.toLowerCase();
          var hit = CODE_SIGLE.filter(function (p) { return s.indexOf(p[0]) >= 0; })[0];
          if (!hit) return m;
          code = hit[1];
        }
        var numsL = nums.replace(/((?:[LRD]\.?\s?)?\d[\d\-]*)/g, function (n) {
          var c = n.replace(/\s+/g, '').replace(/\.$/, '');
          var href = (code === 'CPC' && /^748-\d$/.test(c))
            ? 'article.html?num=' + c
            : '../hub.html#/article/' + code + '/' + encodeURIComponent(c);
          return '<a class="jl-artlink" href="' + href + '" title="art. ' + c + ' ' + code + '">' + n + '</a>';
        });
        return mot + ' ' + numsL + (suite || '');
      });
  }

  /* ═══════════════ Date lue ═════════════════════════════════════════════ */

  function contexte(P) {
    var q = new URLSearchParams(location.search);
    var num = (q.get('num') && P.articles[q.get('num')]) ? q.get('num') : '748-6';
    var today = new Date().toISOString().slice(0, 10);
    var asked = q.get('date') || '';
    var at = /^\d{4}-\d{2}-\d{2}$/.test(asked) ? asked : today;
    return { num: num, today: today, at: at, isToday: at === today };
  }

  function jget(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error(url.replace('../', '') + ' : HTTP ' + r.status);
      return r.json();
    });
  }

  /* ═══════════════ A. LE MODÈLE DE LA CARTE (« maintenant ») ════════════ */

  function loadModel() {
    var P, C = null;
    return jget(DATA).then(function (p) {
      P = p;
      return jget(CITE).catch(function () { return null; });
    }).then(function (c) {
      C = c;
      return build(P, C);
    });
  }

  function build(P, C) {
    var ctx = contexte(P);
    var num = ctx.num, at = ctx.at;
    var versions = P.articles[num].slice().sort(function (x, y) {
      return x.date_debut.localeCompare(y.date_debut);
    });
    var cname = versions[0].titre_text;
    var cur = versions.filter(function (v) {
      return v.date_debut <= at && (v.date_fin || '2999') > at;
    })[0] || null;

    var T = Object.assign({}, P.resolus || {}, P.arretes || {}, P.decrets || {});
    var tOf = function (l) {
      return (l.legitext_resolu && T[l.legitext_resolu]) || T[l.cidtexte] || T[l.id] || null;
    };
    var alive = function (t) { return lifeAt(t, at).k === 'ok'; };

    /* ÉTAGE 1 — le texte qui a écrit la rédaction lue. */
    var etage1 = [];
    if (cur) {
      var seen = new Set();
      cur.liens.forEach(function (l) {
        var isMod = l.typelien === 'MODIFIE' && l.sens === 'cible';
        var isCre = l.typelien === 'CREATION' || l.typelien === 'CREE';
        if (!isMod && !isCre) return;
        var key = l.legitext_resolu || l.cidtexte || l.id;
        if (seen.has(key)) return; seen.add(key);
        var t = tOf(l);
        var brut = clean(l.libelle || l.id).replace(/\s*\([A-Za-z]{1,3}\)\s*$/, '');
        etage1.push({
          rel: isCre ? 'créé par' : 'rédaction en vigueur, telle que modifiée par',
          titre: brut, long: t ? clean(titreArr(t)) : '',
          nature: l.naturetexte || (t && t.nature) || '',
          date: (l.datesignatexte && l.datesignatexte < '2999') ? l.datesignatexte : (t && t.date_texte) || '',
          nor: l.nortexte || (t && t.nor) || '', st: lifeAt(t, at), how: 'lien LEGI',
          lf: legifrance(l.legitext_resolu || l.id || l.cidtexte, l.naturetexte),
          depuis: cur.date_debut
        });
      });
    }

    /* ÉTAGE 2 — décrets en vigueur qui le visent (vide pour un art. réglementaire). */
    var etage2 = Object.keys(P.decrets || {}).map(function (k) { return P.decrets[k]; })
      .filter(function (d) { return (d.vise || []).indexOf(num) >= 0 && alive(d); })
      .sort(function (a, b) { return (b.date_texte || '').localeCompare(a.date_texte || ''); })
      .map(function (d) {
        var t = clean(d.titre), lg = clean(titreArr(d));
        return { rel: 'le vise', titre: t, long: lg !== t ? lg : '', date: d.date_texte || '',
          nor: d.nor || '', st: lifeAt(d, at), how: 'visa', lf: legifrance(d.legitext), nature: 'DECRET' };
      });

    /* ÉTAGE 3 — arrêtés en vigueur pris pour lui, avec retouches et remplacés. */
    var S = P.succession || [];
    var etage3 = Object.keys(P.arretes || {}).map(function (k) { return P.arretes[k]; })
      .filter(function (a) { return (a.vise || []).indexOf(num) >= 0 && alive(a); })
      .sort(function (a, b) { return (b.date_texte || '').localeCompare(a.date_texte || ''); })
      .map(function (a) {
        var seenR = new Set();
        var retouches = S.filter(function (e) {
            return e.de === a.legitext && e.type === 'modifie' && e.vers !== a.legitext;
          })
          .map(function (e) { return T[e.vers]; })
          .filter(function (t) { return t && t.date_debut && t.date_debut <= at; })
          .filter(function (t) { if (seenR.has(t.legitext)) return false; seenR.add(t.legitext); return true; })
          .sort(function (x, y) { return (x.date_texte || '').localeCompare(y.date_texte || ''); })
          .map(function (t) {
            return { rel: 'retouché par', titre: clean(t.titre), long: '', date: t.date_texte || '',
              nor: t.nor || '', st: lifeAt(t, at), how: 'succession',
              lf: legifrance(t.legitext), nature: t.nature || '' };
          });
        var seenP = new Set();
        var remplace = S.filter(function (e) {
            return e.vers === a.legitext && e.type === 'abroge' && e.de !== a.legitext;
          })
          .map(function (e) { return T[e.de]; })
          .filter(function (t) { return t && (t.date_fin || '2999') <= at; })
          .filter(function (t) { if (seenP.has(t.legitext)) return false; seenP.add(t.legitext); return true; })
          .sort(function (x, y) { return (y.date_texte || '').localeCompare(x.date_texte || ''); })
          .map(function (t) { return { titre: clean(t.titre), date: t.date_texte || '', legitext: t.legitext }; });
        var t0 = clean(a.titre), lg = clean(titreArr(a));
        return { rel: 'pris pour lui', titre: t0, long: lg !== t0 ? lg : '', date: a.date_texte || '',
          nor: a.nor || '', st: lifeAt(a, at), how: 'visa', lf: legifrance(a.legitext),
          nature: 'ARRETE', legitext: a.legitext, retouches: retouches, remplace: remplace };
      });

    /* COLONNE DE DROITE — même rang ou plus haut, et qui le MENTIONNE. */
    var seenC = new Set(), citants = new Map();
    var addC = function (key, o) {
      if (!key) return;
      var e = citants.get(key);
      if (e) { if (o.arts) e.arts.push.apply(e.arts, o.arts); e.how.add(o.how1); }
      else {
        var n = Object.assign({}, o);
        n.arts = (o.arts || []).slice(); n.how = new Set([o.how1]);
        citants.set(key, n);
      }
    };
    versions.forEach(function (v) { v.liens.forEach(function (l) {
      if (l.typelien !== 'CITATION' || l.sens !== 'cible') return;
      var k0 = l.id || l.cidtexte; if (seenC.has(k0)) return; seenC.add(k0);
      var t = tOf(l), key = l.legitext_resolu || l.cidtexte || l.id;
      var nature = l.naturetexte || (t && t.nature) || '?';
      var artm = /- art\. ([^ (]+)/.exec(l.libelle || '');
      addC(key, { key: key, nature: nature,
        titre: t ? clean(titreArr(t)) : clean((l.libelle || '').replace(/ - art\..*$/, '')),
        date: (l.datesignatexte && l.datesignatexte < '2999') ? l.datesignatexte : (t && t.date_texte) || '',
        nor: l.nortexte || (t && t.nor) || '', t: t, arts: artm ? [artm[1]] : [],
        how1: 'lien LEGI', lf: legifrance(key, nature) });
    }); });
    Object.keys(P.decrets || {}).forEach(function (k) {
      var d = P.decrets[k];
      if ((d.vise || []).indexOf(num) < 0) return;
      addC(d.legitext, { key: d.legitext, nature: 'DECRET', titre: clean(titreArr(d)),
        date: d.date_texte || '', nor: d.nor || '', t: d, arts: [], how1: 'visa',
        lf: legifrance(d.legitext) });
    });

    /* Les textes qui l'ont ÉCRIT sont dans le cadre normatif ou l'historique,
       jamais à droite ; les arrêtés lui sont inférieurs : à gauche. */
    var auteurs = new Set();
    versions.forEach(function (v) { v.liens.forEach(function (l) {
      if ((l.typelien === 'MODIFIE' && l.sens === 'cible') || l.typelien === 'CREATION' ||
          l.typelien === 'CREE' || l.typelien === 'CODIFICATION') {
        var k = l.legitext_resolu || l.cidtexte || l.id; if (k) auteurs.add(k);
      }
    }); });
    var NATORD = { LOI: 0, ORDONNANCE: 1, DECRET: 2, CODE: 3, ARRETE: 9 };
    var all = Array.from(citants.values());
    var citantsList = all
      .filter(function (c) { return c.nature !== 'ARRETE' && !auteurs.has(c.key); })
      .map(function (c) {
        var n = Object.assign({}, c);
        n.st = lifeAt(c.t, at); n.arts = Array.from(new Set(c.arts));
        return n;
      })
      .sort(function (a, b) {
        return ((NATORD[a.nature] == null ? 5 : NATORD[a.nature]) -
                (NATORD[b.nature] == null ? 5 : NATORD[b.nature])) ||
               (b.date || '').localeCompare(a.date || '');
      });
    var arrCit = all.filter(function (c) { return c.nature === 'ARRETE' && !auteurs.has(c.key); });
    var exclus = {
      auteurs: all.filter(function (c) { return auteurs.has(c.key); }).length,
      arretes_vivants: arrCit.filter(function (c) { return lifeAt(c.t, at).k === 'ok'; }).length,
      arretes_morts: arrCit.filter(function (c) { return lifeAt(c.t, at).k !== 'ok'; }).length
    };

    var sims = versions.map(function (v, i) { return i ? jaccard(versions[i - 1].texte, v.texte) : null; });
    var recycled = sims.some(function (x) { return x !== null && x < 0.25; });

    /* Jurisprudence qui le cite : lexical, doublons Judilibre / JURITEXT fusionnés. */
    var verAt = function (d) {
      return versions.filter(function (v) { return v.date_debut <= d && (v.date_fin || '2999') > d; })[0] || null;
    };
    var juri = [], fusion = 0;
    if (C && C.brut) {
      var byKey = new Map();
      C.brut.forEach(function (x) {
        var k = x.date + '|' + x.juridiction + '|' + (x.extract || '').slice(0, 60);
        var e = byKey.get(k);
        if (e) { e.ids.push(x.id); if (!e.title && x.title) e.title = x.title; }
        else { var n = Object.assign({}, x); n.ids = [x.id]; byKey.set(k, n); }
      });
      juri = Array.from(byKey.values()).map(function (x) {
        var v = verAt(x.date);
        var m = /n° ?([\d./-]+)|, (\d{5,7}),/.exec(x.title || '');
        var n = Object.assign({}, x);
        n.numero = m ? (m[1] || m[2]) : x.ids[0];
        n.v = v; n.differs = v !== cur;
        n.publication = /Publié/.test(x.title || '') ? 'Publié au recueil Lebon'
          : (/Inédit/.test(x.title || '') ? 'Inédit' : '');
        n.href = '../hub.html#/decision/' + x.source + '/' + encodeURIComponent(x.ids[0]);
        n.fam = ({ dila: 'jud', jade: 'adm', cedh: 'eu', cjue: 'eu' })[x.source] || 'jud';
        return n;
      }).sort(function (a, b) { return b.date.localeCompare(a.date); });
      fusion = C.brut.length - juri.length;
    }

    return { P: P, C: C, num: num, cname: cname, versions: versions,
      at: at, today: ctx.today, isToday: ctx.isToday, cur: cur,
      etage1: etage1, etage2: etage2, etage3: etage3,
      citantsList: citantsList, exclus: exclus, sims: sims, recycled: recycled,
      juri: juri, fusion: fusion };
  }

  /* ═══════════════ B. LE MODÈLE DE L'HISTORIQUE ═════════════════════════ */

  /* Règle ferme : A. la vie de l'article (ses rédactions + le texte qui a écrit
     chacune). B. la vie de ce qui est pris pour lui : les arrêtés qui le VISENT,
     vivants ou morts, avec leurs retouches ({de: lui, vers: X, modifie}) et
     leurs prédécesseurs RÉCURSIFS ({de: Y, vers: lui, abroge}). C. rien d'autre.
     Interdit : suivre un lien SORTANT « modifie » d'un arrêté retenu. */
  function loadHisto() {
    return jget(DATA).then(function (P) { return buildHisto(P); });
  }

  function buildHisto(P) {
    var ctx = contexte(P);
    var num = ctx.num, at = ctx.at;
    var T = Object.assign({}, P.resolus || {}, P.arretes || {}, P.decrets || {});
    var S = P.succession || [];
    var versions = P.articles[num].slice().sort(function (x, y) {
      return x.date_debut.localeCompare(y.date_debut);
    });
    var cname = versions[0].titre_text;
    var cur = versions.filter(function (v) {
      return v.date_debut <= at && (v.date_fin || '2999') > at;
    })[0] || null;
    var sims = versions.map(function (v, i) { return i ? jaccard(versions[i - 1].texte, v.texte) : null; });
    var recycled = sims.some(function (x) { return x !== null && x < 0.25; });

    /* A. les rédactions et leur auteur */
    var redactions = versions.map(function (v, i) {
      var auteur = null;
      for (var n = 0; n < v.liens.length; n++) {
        var l = v.liens[n];
        var isMod = l.typelien === 'MODIFIE' && l.sens === 'cible';
        var isCre = l.typelien === 'CREATION' || l.typelien === 'CREE';
        if (!isMod && !isCre) continue;
        var key = l.legitext_resolu || l.cidtexte || l.id;
        var t = T[key] || null;
        auteur = { id: key, titre: clean(l.libelle || l.id).replace(/\s+-\s+art\..*$/, ''),
          art: (/- art\. ([^ (]+)/.exec(l.libelle || '') || [])[1] || '',
          long: t ? clean(titreArr(t)) : '', nature: l.naturetexte || (t && t.nature) || 'DECRET',
          date: (l.datesignatexte && l.datesignatexte < '2999') ? l.datesignatexte : (t && t.date_texte) || '',
          nor: l.nortexte || (t && t.nor) || '', lf: legifrance(key, l.naturetexte) };
        break;
      }
      return { i: i, v: v, debut: v.date_debut, fin: v.date_fin || '2999', texte: v.texte || '',
        nota: v.nota || '', legiarti: v.legiarti, etat: v.etat || '', sim: sims[i], auteur: auteur,
        type: i === 0 ? 'cree' : 'reecrit', lf: legifrance(v.legiarti, 'CODE') };
    });

    /* B. les arrêtés qui visent l'article (niveau 1), vivants ou morts */
    var vises = Object.keys(P.arretes || {}).map(function (k) { return P.arretes[k]; })
      .filter(function (a) { return (a.vise || []).indexOf(num) >= 0; })
      .sort(function (a, b) { return (a.date_debut || '').localeCompare(b.date_debut || ''); });
    var niveau1 = new Set(vises.map(function (a) { return a.legitext; }));

    var mkTexte = function (t, niveau, role) {
      return { id: t.legitext, titre: clean(t.titre), long: clean(titreArr(t)),
        nature: t.nature || 'ARRETE', nor: t.nor || '', debut: t.date_debut || '',
        fin: t.date_fin || '2999', date_texte: t.date_texte || '', etat: t.etat || '',
        nb_articles: t.nb_articles || 0, niveau: niveau, role: role,
        st: lifeAt(t, at), lf: legifrance(t.legitext), raw: t };
    };

    var seenP = new Set();
    var retouchesOf = function (legitext, parent) {
      var seenR = new Set();
      return S.filter(function (e) { return e.de === legitext && e.type === 'modifie' && e.vers !== legitext; })
        .map(function (e) { return T[e.vers]; }).filter(Boolean)
        .filter(function (t) { if (seenR.has(t.legitext)) return false; seenR.add(t.legitext); return true; })
        .sort(function (x, y) { return (x.date_texte || '').localeCompare(y.date_texte || ''); })
        .map(function (t) {
          var R = mkTexte(t, 2, 'retouche');
          R.cible = parent.id; R.parent = parent; R.aussiNiveau1 = niveau1.has(t.legitext);
          return R;
        });
    };
    /* Arbre RÉEL des remplacements : chaque prédécesseur garde ses propres
       prédécesseurs et retouches (2025 abroge 2020 ; 2020 abroge 2009-2011 :
       ceux-là sont sous 2020, jamais à plat sous 2025). */
    var predsOf = function (id, parent, prof) {
      var out = [];
      S.forEach(function (e) {
        if (e.vers !== id || e.type !== 'abroge' || e.de === id) return;
        if (seenP.has(e.de)) return; seenP.add(e.de);
        var t = T[e.de]; if (!t) return;
        var Q = mkTexte(t, 2, 'predecesseur');
        Q.cible = parent.id; Q.parent = parent; Q.prof = prof;
        if (niveau1.has(e.de)) { Q.deja = true; Q.retouches = []; Q.predecesseurs = []; out.push(Q); return; }
        Q.retouches = retouchesOf(e.de, Q);
        Q.predecesseurs = predsOf(e.de, Q, prof + 1);
        out.push(Q);
      });
      return out.sort(function (x, y) { return (y.debut || '').localeCompare(x.debut || ''); });
    };
    var flatPreds = function (a) {
      return a.predecesseurs.filter(function (p) { return !p.deja; })
        .reduce(function (acc2, p) { return acc2.concat([p], flatPreds(p)); }, []);
    };
    var flatRet = function (a) {
      return a.retouches.concat(a.predecesseurs.reduce(function (acc2, p) {
        return acc2.concat(flatRet(p));
      }, []));
    };

    var arretes = vises.map(function (a) {
      var A = mkTexte(a, 1, 'vise');
      A.retouches = retouchesOf(a.legitext, A);
      A.predecesseurs = predsOf(a.legitext, A, 1);
      var ab = S.filter(function (e) { return e.de === a.legitext && e.type === 'abroge' && T[e.vers]; })[0];
      A.abrogePar = ab ? T[ab.vers] : null;
      return A;
    });

    var textes = [];
    arretes.forEach(function (a) {
      textes.push(a);
      flatRet(a).forEach(function (r) { textes.push(r); });
      flatPreds(a).forEach(function (p) { textes.push(p); });
    });
    var kept = new Set(textes.map(function (t) { return t.id; }));

    /* C. les exclus, AVEC leur raison. */
    var exclusIds = new Set(), raison = {};
    S.forEach(function (e) {
      if (kept.has(e.vers) && !kept.has(e.de)) {
        exclusIds.add(e.de); raison[e.de] = 'modifié au passage par un texte retenu';
      }
    });
    arretes.forEach(function (a) {
      if (a.abrogePar && !kept.has(a.abrogePar.legitext)) {
        exclusIds.add(a.abrogePar.legitext);
        raison[a.abrogePar.legitext] = 'a abrogé ' + minus(a.titre) + ' sans viser l’article';
      }
    });
    var exclus = Array.from(exclusIds).map(function (id) { return T[id]; }).filter(Boolean)
      .map(function (t) {
        return { id: t.legitext, titre: clean(t.titre), nor: t.nor || '', date: t.date_texte || '',
          lf: legifrance(t.legitext), raison: raison[t.legitext] || '' };
      })
      .sort(function (a, b) { return (a.date || '').localeCompare(b.date || ''); });

    /* Les événements */
    var ev = [];
    redactions.forEach(function (R) {
      ev.push({ date: R.debut, type: R.type, niveau: 0, red: R,
        label: R.type === 'cree' ? 'créé' : 'réécrit', how: 'lien LEGI',
        quoi: 'art. ' + num + ', rédaction du ' + fmtCourt(R.debut), par: R.auteur,
        st: lifeAt({ date_debut: R.debut, date_fin: R.fin, etat: R.etat }, at) });
    });
    arretes.forEach(function (a) {
      ev.push({ date: a.debut, type: 'pris', niveau: 1, texte: a, label: 'pris pour lui',
        how: 'visa', quoi: a.titre, st: a.st });
      if (a.fin < '2999') ev.push({ date: a.fin, type: 'abroge', niveau: 1, texte: a,
        label: 'abrogé', how: 'succession', quoi: a.titre, st: a.st });
      flatRet(a).forEach(function (r) {
        ev.push({ date: r.date_texte || r.debut, type: 'retouche', niveau: 2, texte: r,
          cible: r.parent, label: 'retouche l’arrêté', how: 'succession', quoi: r.titre, st: r.st });
      });
      flatPreds(a).forEach(function (p) {
        ev.push({ date: p.fin < '2999' ? p.fin : p.debut, type: 'remplace', niveau: 2, texte: p,
          cible: p.parent, label: 'remplacé', how: 'succession', quoi: p.titre, st: p.st });
      });
    });
    ev.sort(function (x, y) {
      return (y.date || '').localeCompare(x.date || '') || (x.niveau - y.niveau);
    });

    var textesU = Array.from(new Map(textes.map(function (t) { return [t.id, t]; })).values());
    var evAt = ev.filter(function (e) { return (e.date || '') <= at; });
    var counts = {
      n0: ev.filter(function (e) { return e.niveau === 0; }).length,
      n1: ev.filter(function (e) { return e.niveau === 1; }).length,
      n2: ev.filter(function (e) { return e.niveau === 2; }).length,
      total: ev.length, avant: evAt.length, apres: ev.length - evAt.length,
      exclus: exclus.length, textes: textesU.length,
      distincts: new Set(textesU.map(function (t) { return t.nor || t.id; })).size,
      vivants: textesU.filter(function (t) { return t.st.k === 'ok'; }).length,
      redactions: redactions.length, arretes: arretes.length
    };

    return { P: P, T: T, num: num, cname: cname, at: at, isToday: ctx.isToday, today: ctx.today,
      versions: versions, cur: cur, redactions: redactions, arretes: arretes, textes: textes,
      ev: ev, exclus: exclus, counts: counts, recycled: recycled, sims: sims };
  }

  /* ═══════════════ C. Chrome partagé par les deux pages ═════════════════ */

  var ICO_CAL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>';

  function whenBadge(M, quoi) {
    return M.isToday
      ? '<span class="jl-when">actuel · ' + fmtCourt(M.at) + '</span>'
      : '<span class="jl-when jl-when--passe" title="vous lisez ' + esc(quoi || 'l’article') +
        ' à une date passée">lu au ' + fmtCourt(M.at) + '</span>';
  }

  /* Popover de date : saisie jj/mm/aaaa, calendrier, saut à une rédaction. */
  function datePopHTML(M, dates) {
    var puces = '<button type="button" class="jl-chip" data-jl-date-chip="' + M.today + '">aujourd’hui</button>' +
      (dates || []).map(function (d) {
        return '<button type="button" class="jl-chip" data-jl-date-chip="' + d + '">' + fmtCourt(d) + '</button>';
      }).join('');
    return '<span class="jl-datew" data-jl-datew>' +
      '<button class="jl-calbtn" data-jl-date-open title="Changer la date de lecture" ' +
      'aria-label="Changer la date de lecture">' + ICO_CAL + '</button>' +
      '<div class="jl-datepop" data-jl-datepop>' +
        '<div class="jl-datepop__k"><label for="jl-date-txt">Saisir une date</label></div>' +
        '<div class="jl-datepop__row">' +
          '<input type="text" id="jl-date-txt" data-jl-date-txt placeholder="jj/mm/aaaa" value="' +
            M.at.slice(8, 10) + '/' + M.at.slice(5, 7) + '/' + M.at.slice(0, 4) + '">' +
          '<button class="jl-bouton jl-bouton--sm" data-jl-date-go>Lire</button></div>' +
        '<div class="jl-datepop__err" data-jl-date-err role="alert"></div>' +
        '<div class="jl-datepop__k"><label for="jl-date-cal">Ou choisir dans le calendrier</label></div>' +
        '<div class="jl-datepop__row"><input type="date" id="jl-date-cal" data-jl-date-cal value="' + M.at + '"></div>' +
        '<div class="jl-datepop__k">Ou sauter à une rédaction</div>' +
        '<div class="jl-datepop__chips">' + puces + '</div>' +
      '</div></span>';
  }

  /* Bande d'identité SANS boîte : État / Rédactions / … / Identifiant / Source. */
  function bandeHTML(cases) {
    return '<div class="jl-bande">' + cases.map(function (c) {
      return '<div><div class="jl-bande__k">' + c.k + '</div><div class="jl-bande__v">' + c.v + '</div></div>';
    }).join('') + '</div>';
  }

  function aide(tip) {
    return '<button type="button" class="jl-aide" data-jl-aide title="' + esc(tip) +
      '" aria-label="' + esc(tip) + '">?</button>';
  }

  global.ART = {
    DATA: DATA, CITE: CITE,
    NATLABEL: NATLABEL, HOWTIP: HOWTIP, SRC: SRC, FAMLABEL: FAMLABEL,
    legifrance: legifrance, lifeAt: lifeAt, minus: minus, clean: clean, titreArr: titreArr,
    acc: acc, words: words, jaccard: jaccard, diffWords: diffWords,
    pill: pill, howHTML: howHTML, linkArts: linkArts, linkArtsLEGI: linkArtsLEGI,
    contexte: contexte, loadModel: loadModel, loadHisto: loadHisto,
    whenBadge: whenBadge, datePopHTML: datePopHTML, bandeHTML: bandeHTML, aide: aide
  };
})(window);
