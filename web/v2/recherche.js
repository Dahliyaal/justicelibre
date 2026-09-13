/**
 * web/v2/recherche.js — la PAGE DE RECHERCHE de la refonte.
 *
 * Aucun style ni script en ligne dans recherche.html : tout le comportement
 * est ici, tous les composants partagés sont dans /styles/jl.css et /jl.js.
 *
 * Ce que cette page reprend du prototype web/hub.html :
 *   rail « Chercher dans », barre réseau + panneau avancé, éclaireur de
 *   référence (citation_only=1), pagination par source avec totaux réels,
 *   pastilles de source avec loader, extraits compactés et coupés, facettes,
 *   tri, flux « Nouveautés ».
 * Ce qu'elle reprend de web/search.html (les 20 points du rapport §5.1) :
 *   voir scratchpad/audit/v2_recherche_13sept.md.
 *
 * ⛔ Règle qui gouverne tout ce fichier : ne JAMAIS dire « aucun résultat »
 *    quand une source n'a pas répondu. Sur un site de droit, un faux négatif
 *    fait conclure qu'un précédent n'existe pas.
 */
(function () {
  'use strict';

  var API = (location.hostname === 'justicelibre.org') ? '' : 'https://justicelibre.org';
  /* La lecture d'une décision ouvre la PAGE SERVEUR /decision/<source>/<id> :
     c'est elle que Google indexe, pas une vue JS. En local, on pointe la prod. */
  var DECISION_BASE = (location.hostname === 'justicelibre.org') ? '/decision' : 'https://justicelibre.org/decision';

  var J, $, $$, esc;      /* renseignés au démarrage, quand JL est chargé */

  /* ─────────────── Tables du fonds (volumes mesurés le 9/09/2026) ─────── */
  var FAMILLES = [
    { k: 'jud', label: 'Judiciaire', fonds: [
      ['cass', 'Cour de cassation', 1092897], ['ca', "Cours d'appel", 601745],
      ['tj', 'Tribunaux judiciaires', 716809]] },
    { k: 'adm', label: 'Administratif', fonds: [
      ['ce', "Conseil d'État", 173812], ['caa', "Cours admin. d'appel", 388654],
      ['ta', 'Tribunaux administratifs', 6514],
      ['opendata', 'Open data TA/CAA', 985996, 'en base, pas encore cherchable']] },
    { k: 'ce-const', label: 'Constitutionnel', fonds: [['constit', 'Conseil constitutionnel', 7388]] },
    { k: 'eu', label: 'Européen', fonds: [['cedh', 'Cour EDH', 76062], ['cjue', 'CJUE', 44665]] }
  ];
  /* Ce qu'une recherche sans filtre atteint réellement (l'open data TA/CAA
     n'y est pas : pas encore cherchable). */
  var TOTAL_TOUT = 3285952;
  var JURI_SOURCES = { cass: 'dila', ca: 'dila', tj: 'dila', constit: 'dila',
    ce: 'ariane,admin', caa: 'admin', ta: 'admin', cedh: 'cedh', cjue: 'cjue' };
  var JURI_LABEL = {};
  FAMILLES.forEach(function (f) { f.fonds.forEach(function (x) { JURI_LABEL[x[0]] = x[1]; }); });
  var FAM_DE = {};   /* fonds → famille, pour le menu à deux niveaux */
  FAMILLES.forEach(function (f) { f.fonds.forEach(function (x) { FAM_DE[x[0]] = f.k; }); });
  var PAGE = 30;
  /* Nom court du BACKEND interrogé (axe 1). Distinct de la famille
     juridictionnelle (axe 2, .jl-tag) : les deux ne disent pas la même chose. */
  var BACKEND = { dila: 'DILA', ariane: 'ArianeWeb', admin: 'JADE', cedh: 'HUDOC',
    cjue: 'EUR-Lex', doctrine: 'doctrine', legi: 'LEGI' };

  /* ─────────────── État ───────────────────────────────────────────────── */
  var S = {
    q: '', juri: [], lieu: '', formation: '', dateMin: '', dateMax: '',
    thes: true, sort: 'pertinence', mode: 'sommaire',
    results: [], srcState: {}, facet: {}, pager: null,
    avert: [], citation: null, citationNote: '', seq: 0, enVol: false, advOpen: false
  };

  /* ═══════════════ 1. Panneau avancé ═══════════════════════════════════ */

  function renderFams() {
    var sel = new Set(S.juri);
    $('#fams').innerHTML = FAMILLES.map(function (f) {
      var ok = f.fonds.filter(function (x) { return !x[3]; });
      var n = ok.filter(function (x) { return sel.has(x[0]); }).length;
      var etat = n === ok.length ? ' is-on' : (n ? ' is-half' : '');
      return '<div><div class="jl-fam__h">' + esc(f.label) +
        '<button type="button" class="jl-fam__all' + etat + '" data-fam="' + f.k +
        '" title="Tout / rien" aria-label="Tout sélectionner : ' + esc(f.label) + '"></button></div>' +
        f.fonds.map(function (x) {
          if (x[3]) {
            return '<button type="button" class="jl-fch is-soon" disabled aria-disabled="true" title="' +
              esc(x[3]) + '"><i></i><span>' + esc(x[1]) + '</span><span class="jl-fch__n">bientôt</span></button>';
          }
          return '<button type="button" class="jl-fch' + (sel.has(x[0]) ? ' is-on' : '') +
            '" data-j="' + x[0] + '" aria-pressed="' + (sel.has(x[0]) ? 'true' : 'false') + '"><i></i><span>' +
            esc(x[1]) + '</span><span class="jl-fch__n">' + J.fmtN(x[2]) + '</span></button>';
        }).join('') + '</div>';
    }).join('');
    $$('#fams .jl-fch[data-j]').forEach(function (b) {
      b.onclick = function () {
        var k = b.dataset.j, i = S.juri.indexOf(k);
        if (i < 0) S.juri.push(k); else S.juri.splice(i, 1);
        majAvance();
      };
    });
    $$('#fams .jl-fam__all').forEach(function (b) {
      b.onclick = function () {
        var f = FAMILLES.filter(function (x) { return x.k === b.dataset.fam; })[0];
        var ok = f.fonds.filter(function (x) { return !x[3]; }).map(function (x) { return x[0]; });
        var tout = ok.every(function (k) { return S.juri.indexOf(k) >= 0; });
        ok.forEach(function (k) {
          var i = S.juri.indexOf(k);
          if (tout && i >= 0) S.juri.splice(i, 1);
          else if (!tout && i < 0) S.juri.push(k);
        });
        majAvance();
      };
    });
  }

  /* Le menu à deux niveaux (groupe « Administratif » = ses trois fonds) est
     SYNCHRONISÉ avec les cases : c'est le PARENT_OF de search.html:1053-1059,
     transposé sur une sélection multiple. */
  function majMenuJuri() {
    var lab = 'Toutes juridictions';
    if (S.juri.length === 1) lab = JURI_LABEL[S.juri[0]] || S.juri[0];
    else if (S.juri.length > 1) {
      var fams = new Set(S.juri.map(function (k) { return FAM_DE[k]; }));
      var f0 = FAMILLES.filter(function (f) { return f.k === [].concat(Array.from(fams))[0]; })[0];
      var tousDeLaFam = fams.size === 1 && f0 &&
        f0.fonds.filter(function (x) { return !x[3]; }).length === S.juri.length;
      lab = tousDeLaFam ? 'Tout ' + f0.label.toLowerCase() : S.juri.length + ' fonds choisis';
    }
    var d = $('#juriMenu [data-jl-menu-value]');
    if (d) d.textContent = lab;
    $$('#juriMenu .jl-menu__item, #juriMenu .jl-menu__group').forEach(function (it) {
      var v = it.dataset.value;
      var on = v ? (S.juri.indexOf(v) >= 0 ||
        (FAMILLES.some(function (f) { return f.k === v; }) &&
         S.juri.some(function (k) { return FAM_DE[k] === v; }))) : !S.juri.length;
      it.classList.toggle('is-selected', !!on);
    });
  }

  /* Filtre par lieu (INSTANCES search.html:958-996) : n'apparaît que lorsque
     la sélection porte sur UN fonds local (TA, CAA, CA). */
  function majLieuEtChambre() {
    var seul = S.juri.length === 1 ? S.juri[0] : '';
    var items = J.INSTANCES[seul];
    if (items) {
      $('#champLieu').hidden = false;
      var pl = seul === 'ta' ? 'Tous TA' : seul === 'caa' ? 'Toutes CAA' : 'Toutes CA';
      remplirMenu('#lieuMenu', pl, items.map(function (x) {
        return { value: x[0], label: x[1] + ' (' + x[0] + ')' };
      }), function (v) { S.lieu = v; });
      if (!S.lieu) $('#lieuMenu [data-jl-menu-value]').textContent = pl;
    } else { $('#champLieu').hidden = true; S.lieu = ''; }

    var chambres = J.FORMATIONS_FILTRABLES[seul] || (S.juri.indexOf('cass') >= 0 ? J.FORMATIONS_FILTRABLES.cass : null);
    if (chambres) {
      $('#champChambre').hidden = false;
      remplirMenu('#formMenu', 'Toutes', chambres.map(function (f) { return { value: f, label: f }; }),
        function (v) { S.formation = v; });
    } else { $('#champChambre').hidden = true; S.formation = ''; }
  }

  function remplirMenu(sel, placeholder, options, onPick) {
    var wrap = $(sel), panel = wrap.querySelector('.jl-menu__panel');
    var sig = placeholder + '|' + options.map(function (o) { return o.value; }).join(',');
    wrap._onPick = onPick;
    if (wrap._sig === sig) return;   /* ne pas reconstruire : la sélection serait perdue */
    wrap._sig = sig;
    panel.innerHTML = '<div class="jl-menu__item is-selected" data-value="" data-label="' +
      esc(placeholder) + '">' + esc(placeholder) + '</div>' +
      options.map(function (o) {
        return '<div class="jl-menu__item" data-value="' + esc(o.value) + '" data-label="' +
          esc(o.label) + '">' + esc(o.label) + '</div>';
      }).join('');
    if (!wrap._lie) {
      wrap._lie = true;
      wrap.addEventListener('jl:pick', function (e) { (wrap._onPick || function () {})(e.detail.value); majAvance(); });
      J.bindMenu(wrap.parentNode);
    }
  }

  function nbFiltres() {
    return S.juri.length + (S.lieu ? 1 : 0) + (S.formation ? 1 : 0) +
      ((S.dateMin || S.dateMax) ? 1 : 0) + (S.thes ? 0 : 1);
  }
  function resumeFiltres() {
    var out = [];
    S.juri.forEach(function (k) { out.push({ k: 'juridiction', v: k, label: JURI_LABEL[k] || k }); });
    if (S.lieu) out.push({ k: 'lieu', v: S.lieu, label: 'lieu : ' + S.lieu });
    if (S.formation) out.push({ k: 'formation', v: S.formation, label: S.formation });
    if (!S.thes) out.push({ k: 'thes', v: '0', label: 'mots exacts, sans thésaurus' });
    if (S.dateMin || S.dateMax) {
      out.push({ k: 'dates', v: '', label: S.dateMin && S.dateMax
        ? J.fmtCourt(S.dateMin) + ' → ' + J.fmtCourt(S.dateMax)
        : S.dateMin ? 'depuis le ' + J.fmtCourt(S.dateMin) : "jusqu'au " + J.fmtCourt(S.dateMax) });
    }
    return out;
  }

  function majAvance() {
    renderFams(); majMenuJuri(); majLieuEtChambre();
    var n = nbFiltres(), c = $('#advCount');
    c.hidden = !n; c.textContent = n || '';
    $('#advT').classList.toggle('is-on', !!n || S.advOpen);
    $('#advClear').hidden = !n;
    var r = resumeFiltres();
    $('#advSummary').textContent = r.map(function (x) { return x.label; }).join(' · ') ||
      'Toute la jurisprudence, toutes dates.';
    var sel = new Set(S.juri);
    var tot = sel.size ? FAMILLES.reduce(function (a, f) {
      return a + f.fonds.reduce(function (b, x) { return b + (sel.has(x[0]) && !x[3] ? x[2] : 0); }, 0);
    }, 0) : TOTAL_TOUT;
    $('#lead').innerHTML = J.nb(tot) + ' décisions interrogeables · ' +
      "Cassation, cours d'appel, tribunaux judiciaires, Conseil d'État, cours et tribunaux " +
      'administratifs, Conseil constitutionnel, Cour EDH, CJUE.';
    majRecapImpression();
  }

  /* ═══════════════ 2. URL partageable (query string, pas un hash) ══════ */

  /* search.html:2361-2373 : l'URL suit la recherche, donc elle est
     partageable et citable. On garde la QUERY STRING (et pas un hash) pour
     que l'adresse reste une vraie URL de page. */
  function syncUrl() {
    var p = new URLSearchParams();
    if (S.q) p.set('q', S.q);
    if (S.juri.length) p.set('juridiction', S.juri.join(','));
    if (S.lieu) p.set('lieu', S.lieu);
    if (S.formation) p.set('formation', S.formation);
    if (S.dateMin) p.set('date_min', S.dateMin);
    if (S.dateMax) p.set('date_max', S.dateMax);
    if (S.sort !== 'pertinence') p.set('sort', S.sort);
    if (!S.thes) p.set('thes', '0');
    var force = new URLSearchParams(location.search).get('timeout');
    if (force) p.set('timeout', force);
    try { history.replaceState(null, '', location.pathname + (p.toString() ? '?' + p : '')); } catch (e) {}
  }

  function lireUrl() {
    var p = new URLSearchParams(location.search);
    S.q = p.get('q') || '';
    S.juri = (p.get('juridiction') || '').split(',').filter(function (x) { return JURI_SOURCES[x]; });
    S.lieu = p.get('lieu') || '';
    S.formation = p.get('formation') || '';
    S.dateMin = p.get('date_min') || '';
    S.dateMax = p.get('date_max') || '';
    S.sort = p.get('sort') || 'pertinence';
    S.thes = p.get('thes') !== '0';
    $('#q').value = S.q;
    $('#dateMin').value = S.dateMin;
    $('#dateMax').value = S.dateMax;
    $('#thesT').classList.toggle('is-on', S.thes);
    $('#thesT').setAttribute('aria-pressed', S.thes ? 'true' : 'false');
    if (nbFiltres()) ouvrirAvance(true);
  }

  function majRecapImpression() {
    var r = resumeFiltres();
    $('#recapImpression').innerHTML =
      '<b>justicelibre.org — recherche</b><br>Requête : ' + (S.q ? '« ' + esc(S.q) + ' »' : '(vide)') +
      '<br>Filtres : ' + esc(r.map(function (x) { return x.label; }).join(' · ') || 'aucun') +
      '<br>Adresse : ' + esc(location.href);
  }

  /* ═══════════════ 3. Recherche ════════════════════════════════════════ */

  function plans() {
    if (S.juri.length) {
      return S.juri.map(function (j) { return { sources: JURI_SOURCES[j], juridiction: j }; });
    }
    return [{ sources: 'dila' }, { sources: 'ariane' }, { sources: 'admin' },
            { sources: 'cedh' }, { sources: 'cjue' }];
  }
  function cle(pl) {
    return pl.juridiction ? (JURI_LABEL[pl.juridiction] || pl.juridiction)
                          : (J.SOURCE_NAMES[pl.sources] || pl.sources);
  }

  /* Garde-fou double envoi : « Double-clic sur Chercher (ou Entrée répétée) :
     la même recherche partait deux fois et doublait les cartes »
     (search.html:2344-2345). */
  function lancer() {
    var q = $('#q').value.trim();
    if (S.enVol && q === S.q) return;
    S.q = q;
    syncUrl();
    if (!q) {
      S.results = []; S.srcState = {}; S.pager = null; S.citation = null;
      $('#srcState').innerHTML = ''; $('#topline').innerHTML = ''; $('#avertissements').innerHTML = '';
      $('#liste').innerHTML = '<p class="jl-muted">Saisissez une requête pour lancer une recherche.</p>';
      $('#expBar').hidden = true;
      $('#flux').hidden = false;
      return;
    }
    S.enVol = true;
    $('#goBtn').disabled = true;
    chercher().then(fini, fini);
    function fini() { S.enVol = false; $('#goBtn').disabled = false; }
  }

  async function chercher() {
    var seq = ++S.seq, q = S.q;
    S.results = []; S.srcState = {}; S.facet = {}; S.avert = [];
    S.citation = null; S.citationNote = '';
    $('#flux').hidden = true;
    $('#avertissements').innerHTML = '';
    $('#liste').innerHTML = '<p class="jl-muted"><span class="jl-spin"></span> Recherche en cours…</p>';
    montrerExpansion(q);

    /* Éclaireur de référence : si le serveur reconnaît une citation
       (n° de pourvoi, ECLI, juridiction + date), il la résout en précision
       maximale et on s'arrête là — pas de recherche lexicale qui exigerait
       « Cass. » ou « sept. » dans le texte de l'arrêt. */
    if (!S.juri.length) {
      try {
        var pre = await fetch(API + '/api/search?q=' + encodeURIComponent(q) + '&limit=30&citation_only=1');
        var pd = pre.ok ? await pre.json() : null;
        if (seq !== S.seq) return;
        if (pd && pd.citation_match) {
          S.results = pd.results || [];
          plans().forEach(function (pl) {
            S.srcState[cle(pl)] = (pd.per_source || {})[pl.sources]
              ? { etat: 'ok' } : { etat: 'hors', why: 'non interrogée (référence reconnue)' };
          });
          S.citation = pd.citation_parsed || null;
          S.citationNote = pd.note || '';
          S.pager = null;
          renderSources(); renderResults();
          return;
        }
      } catch (e) { /* éclaireur muet : parcours classique */ }
    }

    S.pager = { q: q, seq: seq, plans: plans(), page: {}, total: {}, exact: {}, busy: false };
    S.pager.plans.forEach(function (pl) { S.srcState[cle(pl)] = { etat: 'run' }; });
    renderSources();
    await interroger(S.pager.plans, 0, 20);
    if (seq !== S.seq) return;
    renderResults();
    /* Relance automatique, en arrière-plan, des sources en DÉLAI (pas des
       refus 4xx : les rejouer serait voué au même refus, search.html:2497). */
    await relancerLesDelais();
  }

  async function interroger(pls, offset, timeout) {
    var P = S.pager, seq = P.seq;
    await Promise.all(pls.map(async function (pl) {
      var k = cle(pl);
      /* ?timeout=N dans l'adresse force le délai envoyé à l'API. Sert à
         PROVOQUER l'état « source en délai » pour le vérifier (timeout=1). */
      var force = new URLSearchParams(location.search).get('timeout');
      var params = new URLSearchParams({ q: P.q, limit: String(PAGE), offset: String(offset),
        sources: pl.sources, timeout: String(force || timeout || 20) });
      if (pl.juridiction) params.set('juridiction', pl.juridiction);
      if (S.lieu) params.set('lieu', S.lieu);
      if (S.formation && pl.juridiction === 'cass') params.set('formation', S.formation);
      if (S.dateMin) params.set('date_min', S.dateMin);
      if (S.dateMax) params.set('date_max', S.dateMax);
      if (S.sort !== 'pertinence') params.set('sort', S.sort);
      if (S.thes) params.set('expand', '1');
      try {
        var r = await fetch(API + '/api/search?' + params);
        var ct = r.headers.get('content-type') || '';
        if (ct.indexOf('json') < 0) throw new Error('HTTP ' + r.status);
        var d = await r.json();
        if (seq !== S.seq) return;
        /* DISTINCTION refus déterministe / délai dépassé (search.html:2496-2502).
           Un 4xx est un REFUS : on l'affiche tel quel et on ne le rejoue pas. */
        if (r.status >= 400 && r.status < 500) {
          S.srcState[k] = { etat: 'refus', why: d.error || ('HTTP ' + r.status) };
          return;
        }
        if (d.error) { S.srcState[k] = { etat: 'refus', why: d.error }; return; }
        (d.filtres_ignores || []).forEach(function (f) { S.avert.push(f); });
        var muettes = pl.sources.split(',').every(function (s) {
          return (d.sources_no_result || d.sources_en_echec || []).indexOf(s) >= 0;
        });
        var recus = (d.results || []).length;
        if (muettes && !recus) S.srcState[k] = { etat: 'delai', why: "n'a pas répondu à temps (" + (timeout || 20) + ' s)' };
        else S.srcState[k] = { etat: 'ok', n: recus };
        var vus = new Set(S.results.map(function (x) { return x.source + ':' + x.id; }));
        (d.results || []).forEach(function (x) {
          var id = x.source + ':' + x.id;
          if (!vus.has(id)) { vus.add(id); S.results.push(x); }
        });
        if (typeof d.total === 'number' && (offset === 0 || d.total > 0)) {
          P.total[k] = d.total;
          P.exact[k] = d.total_exact !== false;
        }
        var suivant = offset + PAGE;
        P.page[k] = { offset: suivant,
          more: recus > 0 && (P.total[k] !== undefined ? suivant < P.total[k] : recus >= PAGE) };
      } catch (e) {
        if (seq !== S.seq) return;
        S.srcState[k] = { etat: 'delai', why: e.message || 'pas de réponse' };
      }
      renderSources(); renderResults();
    }));
  }

  /* Relance automatique des sources en délai, avec un second délai de 60 s
     (search.html:2535-2547). Le second appel aboutit presque toujours :
     l'index est alors en cache. */
  async function relancerLesDelais() {
    if (!S.pager) return;
    var aRejouer = S.pager.plans.filter(function (pl) {
      var st = S.srcState[cle(pl)];
      return st && st.etat === 'delai';
    });
    if (!aRejouer.length) return;
    aRejouer.forEach(function (pl) { S.srcState[cle(pl)] = { etat: 'run', why: 'seconde tentative, 60 s' }; });
    renderSources(); renderResults();
    await interroger(aRejouer, 0, 60);
    renderResults();
  }

  /* ═══════════════ 4. Pastilles de source ══════════════════════════════ */

  function renderSources() {
    var el = $('#srcState');
    var ks = Object.keys(S.srcState);
    if (!ks.length) { el.innerHTML = ''; return; }
    el.innerHTML = ks.map(function (k) {
      var st = S.srcState[k];
      var m = {
        run: ['jl-pastille--loader', st.why || 'interrogation en cours'],
        ok: ['jl-pastille--ok', 'a répondu' + (st.n != null ? ' · ' + st.n + ' sur cette page' : '')],
        delai: ['jl-pastille--morte', st.why || "n'a pas répondu à temps"],
        refus: ['jl-pastille--q', 'refus du serveur : ' + (st.why || '')],
        hors: ['jl-pastille--q', st.why || 'non interrogée']
      }[st.etat] || ['jl-pastille--q', 'état inconnu'];
      var suffixe = st.etat === 'delai' ? ' · délai' : st.etat === 'refus' ? ' · refus' : '';
      return '<span class="jl-pastille ' + m[0] + '" title="' + esc(k + ' : ' + m[1]) + '">' +
        esc(k) + esc(suffixe) + '</span>';
    }).join('');
  }

  function sourcesMuettes() {
    return Object.keys(S.srcState).filter(function (k) { return S.srcState[k].etat === 'delai'; });
  }
  function sourcesRefus() {
    return Object.keys(S.srcState).filter(function (k) { return S.srcState[k].etat === 'refus'; });
  }
  function enCours() {
    return Object.keys(S.srcState).some(function (k) { return S.srcState[k].etat === 'run'; });
  }

  /* ═══════════════ 5. Résultats ════════════════════════════════════════ */

  function filtres() {
    return S.results.filter(function (r) {
      return (!S.facet.fam || J.FAM(r) === S.facet.fam) &&
             (!S.facet.juri || r.juridiction === S.facet.juri) &&
             (!S.facet.an || String(r.date || '').slice(0, 4) === S.facet.an) &&
             (!S.facet.src || r.source === S.facet.src);
    });
  }

  function renderResults() {
    var liste = $('#liste'), tl = $('#topline');
    var rows = filtres(), tot = S.results.length;
    var P = S.pager || { total: {}, page: {}, exact: {} };

    /* Avertissements : refus 4xx, filtres ignorés, délais. */
    var av = [];
    sourcesRefus().forEach(function (k) {
      av.push('<div class="jl-alerte jl-alerte--icone" data-espace="haut"><b>⚠</b><div><b>' + esc(k) +
        '</b> a refusé la requête : ' + esc(S.srcState[k].why || '') +
        '. Ce n\'est pas un délai dépassé : rejouer la même requête donnerait le même refus.</div></div>');
    });
    S.avert.forEach(function (f) {
      av.push('<div class="jl-note" data-espace="haut">Filtre non appliqué : <b>' +
        esc(f.parametre || '') + '</b> — ' + esc(f.raison || f.message || '') + '</div>');
    });
    var muettes = sourcesMuettes();
    if (muettes.length && rows.length) {
      av.push('<div class="jl-honnetete" data-espace="haut"><b>Recherche incomplète.</b> ' +
        esc(muettes.join(', ')) + (muettes.length > 1 ? " n'ont" : " n'a") +
        ' pas répondu : les résultats ci-dessous ne couvrent pas ' +
        (muettes.length > 1 ? 'ces fonds' : 'ce fonds') +
        '. <button type="button" class="jl-bouton jl-bouton--ghost jl-bouton--sm" data-relancer>Relancer</button></div>');
    }
    $('#avertissements').innerHTML = av.join('');
    $$('#avertissements [data-relancer]').forEach(function (b) { b.onclick = lancer; });

    /* Bandeau de tête : compteurs réels, mode, tri. */
    var known = Object.keys(P.total).reduce(function (a, k) { return a + P.total[k]; }, 0);
    var exact = Object.keys(P.total).every(function (k) { return P.exact[k] !== false; });
    tl.innerHTML = S.q ? '<div class="jl-topline">' +
      '<span class="jl-serif jl-compte">' + J.nb(rows.length) +
      (rows.length !== tot ? ' <span class="jl-muted jl-petit">sur ' + J.nb(tot) + ' chargés</span>'
        : (rows.length === 1 ? ' résultat chargé' : ' résultats chargés')) +
      (known > tot ? ' <span class="jl-muted jl-petit">sur ' + J.nb(known) +
        (exact ? '' : ' environ') + ' existants</span>' : '') + '</span>' +
      '<span class="jl-muted jl-petit">' +
      (S.citation ? 'mode <b class="jl-teal">référence</b> · numéro reconnu, le reste de la requête est ignoré'
                  : 'mode <b class="jl-teal">lexical</b> · tous les mots exigés') + '</span>' +
      '<span class="jl-vue jl-vue--sm">' +
        '<button type="button" class="' + (S.mode === 'sommaire' ? 'is-on' : '') + '" data-mode="sommaire">Sommaire</button>' +
        '<button type="button" class="' + (S.mode === 'extrait' ? 'is-on' : '') + '" data-mode="extrait">Extrait</button></span>' +
      '<span class="jl-vue jl-vue--sm">' +
        '<button type="button" class="' + (S.sort === 'pertinence' ? 'is-on' : '') + '" data-sort="pertinence">Pertinence</button>' +
        '<button type="button" class="' + (S.sort === 'date_desc' ? 'is-on' : '') + '" data-sort="date_desc">Récent</button>' +
        '<button type="button" class="' + (S.sort === 'date_asc' ? 'is-on' : '') + '" data-sort="date_asc">Ancien</button></span>' +
      '</div>' +
      (S.citation ? '<div class="jl-note">Référence reconnue' +
        (S.citation.numeros && S.citation.numeros.length ? ' : <b>' +
          esc(S.citation.numeros.map(function (n) { return n.replace(/^[a-z]+:/, ''); }).join(', ')) + '</b>' : '') +
        (S.citation.date ? ' · ' + esc(J.fmtDate(S.citation.date)) : '') +
        (S.citationNote ? ' — ' + esc(S.citationNote) : '') + '</div>' : '') : '';
    $$('#topline [data-mode]').forEach(function (b) { b.onclick = function () { S.mode = b.dataset.mode; renderResults(); }; });
    $$('#topline [data-sort]').forEach(function (b) {
      b.onclick = function () { S.sort = b.dataset.sort; syncUrl(); lancer(); };
    });
    $('#advSum').innerHTML = resumeFiltres().map(function (c) {
      return '<button type="button" class="jl-filtre is-on" data-rm="' + esc(c.k) + ':' + esc(c.v) + '">' +
        esc(c.label) + ' ✕</button>';
    }).join('');
    $$('#advSum [data-rm]').forEach(function (b) {
      b.onclick = function () {
        var p = b.dataset.rm.split(':'), k = p[0], v = p.slice(1).join(':');
        if (k === 'juridiction') { var i = S.juri.indexOf(v); if (i >= 0) S.juri.splice(i, 1); }
        else if (k === 'lieu') S.lieu = '';
        else if (k === 'formation') S.formation = '';
        else if (k === 'thes') S.thes = true;
        else { S.dateMin = ''; S.dateMax = ''; $('#dateMin').value = ''; $('#dateMax').value = ''; }
        majAvance(); lancer();
      };
    });

    if (!S.q) { liste.innerHTML = ''; return; }

    /* ⛔ Le cœur du point 1 du rapport : trois « vides » distincts. */
    if (!rows.length) {
      if (enCours()) {
        liste.innerHTML = '<p class="jl-muted" data-espace="haut"><span class="jl-spin"></span> Recherche en cours…</p>';
      } else if (muettes.length) {
        liste.innerHTML = '<div class="jl-honnetete" data-espace="haut">' +
          '<b>Recherche incomplète.</b> ' + (muettes.length > 1 ? 'Les fonds ' : 'Le fonds ') +
          esc(muettes.join(', ')) +
          (muettes.length > 1 ? " n'ont" : " n'a") + ' pas répondu à temps : ce « rien » ne veut pas dire ' +
          "qu'il n'y a rien. Aucune conclusion ne peut être tirée de cette absence. " +
          '<button type="button" class="jl-bouton jl-bouton--ghost jl-bouton--sm" data-relancer>Relancer</button></div>';
        $$('#liste [data-relancer]').forEach(function (b) { b.onclick = lancer; });
      } else if (sourcesRefus().length === Object.keys(S.srcState).length && Object.keys(S.srcState).length) {
        liste.innerHTML = '<p class="jl-muted" data-espace="haut">Toutes les sources ont refusé la requête (voir ci-dessus).</p>';
      } else {
        liste.innerHTML = '<p class="jl-muted" data-espace="haut">Aucun résultat. ' +
          'Toutes les sources interrogées ont répondu : il n\'y a rien pour cette requête. ' +
          'Essayez des mots plus larges, ou enlevez des filtres.</p>';
      }
      return;
    }

    /* Ordre : entrelacement par source en pertinence (JL.entrelacer). */
    var ordonnes = S.sort === 'date_desc'
      ? rows.slice().sort(function (a, b) { return (b.date || '0000-00-00').localeCompare(a.date || '0000-00-00'); })
      : S.sort === 'date_asc'
      ? rows.slice().sort(function (a, b) { return (a.date || '9999-12-31').localeCompare(b.date || '9999-12-31'); })
      : J.entrelacer(rows);

    liste.innerHTML = ordonnes.map(carteResultat).join('') + boutonSuite() + facettes();
    lierFacettes();
    var mb = $('#plusBtn');
    if (mb) mb.onclick = chargerSuite;
  }

  function carteResultat(r) {
    var fam = J.FAM(r), f = J.fmtFormation(r.formation);
    var vide = function (v) { return !v || v === 'undefined' || v === 'null' || !String(v).trim(); };
    /* Extrait : les retours à la ligne bruts de l'en-tête sont compactés ;
       le sommaire officiel garde ses paragraphes. Puis coupe à 420 car. */
    var brut = (S.mode === 'sommaire' && r.sommaire) ? r.sommaire
      : String(r.extract || '').replace(/[ \t]*\n[ \t\n_]*/g, ' · ').replace(/\s{2,}/g, ' ')
        .replace(/^(…|\.\.\.)?\s*·\s*/, '…').trim();
    var sum = J.clipExtract(brut, 420);
    var kind = (S.mode === 'sommaire' && r.sommaire) ? '<span class="jl-off">sommaire officiel</span>'
      : (r.extract ? '<span class="jl-muted">extrait</span>' : '<span class="jl-warnp">pas d’extrait renvoyé</span>');
    /* Les articles cités DANS L'EXTRAIT deviennent cliquables : JL.lierArticles
       (= highlightLawRefs de search.html:1246-1414, repris tel quel). */
    var html = sum ? J.lierArticles(J.surlignerExtrait(sum, S.q, 420)) : '';
    var off = J.sourceOfficielle(r.id, r.numero);
    var href = DECISION_BASE + '/' + encodeURIComponent(r.source) + '/' + encodeURIComponent(r.id);
    return '<article class="jl-resultat" data-date="' + esc(r.date || '') + '">' +
      '<div class="jl-resultat__meta">' +
        /* AXE 1 = le backend interrogé (⛔ jamais la famille juridictionnelle,
           qui est l'axe 2 juste à côté : piège n° 3 du normaliseur). */
        '<span class="jl-src-badge jl-src-badge--' + (J.SRC_BADGES[r.source] || 'admin') +
          '" title="' + esc('Fonds interrogé : ' + (J.SOURCE_NAMES[r.source] || r.source)) + '">' +
          esc(BACKEND[r.source] || r.source) + '</span>' +
        '<span class="jl-tag jl-tag--' + fam + '">' + esc(J.FAMLABEL[fam]) + '</span>' +
        (vide(r.juridiction) ? '<span class="jl-vide">juridiction non renseignée</span>'
          : '<span>' + esc(r.juridiction) + (f ? ' · ' + esc(f) : '') + '</span>') +
        (vide(r.date) ? '<span class="jl-vide">date -</span>' : '<span>' + esc(J.fmtDate(r.date)) + '</span>') +
      '</div>' +
      '<h3 class="jl-resultat__t"><a href="' + esc(href) + '">' +
        esc(String(r.title || '(sans titre)').replace(/\b(\d{4}-\d{2}-\d{2})\b/g, function (m) { return J.fmtDate(m); })) +
      '</a></h3>' +
      (html ? '<p class="jl-resultat__x">' + html + '</p>' : '') +
      '<div class="jl-resultat__ref">' +
        (vide(r.numero) ? '<span class="jl-vide">n° -</span>' : '<span>n° ' + esc(r.numero) + '</span>') +
        '<span>·</span>' +
        (vide(r.ecli) ? '<span class="jl-vide">ECLI -</span>' : '<span>' + esc(r.ecli) + '</span>') +
        '<span>·</span><span class="jl-muted">' + esc(J.SOURCE_NAMES[r.source] || r.source) + '</span>' +
        '<span>·</span>' + kind +
        (off ? '<span>·</span><a href="' + esc(off.url) + '" target="_blank" rel="external noopener nofollow">' +
          esc(off.label) + ' ↗</a>'
          /* ⚠ search.html:2111 teste ^(DCE_|DCAA_|DTA_|ORTA_) ; les identifiants
             réellement servis par l'API sont en DCA_ (ex. DCA_22NC02724_…),
             que ce motif NE COUVRE PAS. L'encadré honnête ne s'affichait donc
             jamais pour les CAA. On ajoute DCA_ ICI, à l'affichage, sans
             toucher à JL.sourceOfficielle qui reste la copie exacte. */
          : (/^(DCE_|DCA_|DCAA_|DTA_|ORTA_)/.test(r.id || '')
            ? '<span>·</span><span class="jl-provenance" title="Open data du Conseil d\'État (loi du 7 octobre 2016, art. 20-21). Cette décision n\'est pas publiée au Recueil Lebon : Légifrance ne l\'indexe pas. Pas de bouton vers une page qui n\'existe pas.">pas de page officielle</span>'
            : '')) +
        '<span>·</span><button type="button" class="jl-provenance" data-signal="' + esc(r.source + ':' + r.id) +
          '" data-titre="' + esc(r.title || '') + '" title="Signaler un problème sur cette décision">signaler</button>' +
      '</div></article>';
  }

  function boutonSuite() {
    var P = S.pager;
    if (!P) return '';
    var restants = Object.keys(P.page).filter(function (k) { return P.page[k].more; });
    if (!restants.length) return '';
    return '<div class="jl-plus"><button type="button" class="jl-bouton jl-bouton--cta" id="plusBtn"' +
      (P.busy ? ' disabled' : '') + '>' + (P.busy ? 'Chargement…' : 'Charger la suite') + '</button>' +
      '<div class="jl-plus__detail">' + restants.map(function (k) {
        return esc(k) + ' : ' + J.nb(P.page[k].offset) +
          (P.total[k] !== undefined ? ' / ' + J.nb(P.total[k]) + (P.exact[k] === false ? ' env.' : '') : '');
      }).join(' · ') + '</div></div>';
  }

  /* Chaque source repart de SON offset : elles n'avancent pas au même rythme. */
  async function chargerSuite() {
    var P = S.pager;
    if (!P || P.busy) return;
    P.busy = true; renderResults();
    var pls = P.plans.filter(function (pl) { var p = P.page[cle(pl)]; return p && p.more; });
    pls.forEach(function (pl) { S.srcState[cle(pl)] = { etat: 'run' }; });
    renderSources();
    for (var i = 0; i < pls.length; i++) {
      await interroger([pls[i]], P.page[cle(pls[i])].offset, 20);
    }
    P.busy = false; renderResults();
  }

  /* ═══════════════ 6. Facettes (sur les résultats chargés) ═════════════ */

  function facettes() {
    if (!S.results.length) return '';
    var compte = function (f) {
      var m = new Map();
      S.results.forEach(function (r) { var k = f(r); if (k) m.set(k, (m.get(k) || 0) + 1); });
      return Array.from(m).sort(function (a, b) { return b[1] - a[1]; });
    };
    var annees = compte(function (r) { return String(r.date || '').slice(0, 4); })
      .sort(function (a, b) { return a[0].localeCompare(b[0]); });
    var max = Math.max.apply(null, [1].concat(annees.map(function (y) { return y[1]; })));
    var fr = function (k, list, lim) {
      return list.slice(0, lim || 8).map(function (x) {
        return '<button type="button" class="jl-frow' + (S.facet[k] === x[0] ? ' is-on' : '') +
          '" data-facet="' + k + '=' + esc(x[0]) + '"><span>' +
          esc(k === 'fam' ? (J.FAMLABEL[x[0]] || x[0]) : k === 'src' ? (J.SOURCE_NAMES[x[0]] || x[0]) : x[0]) +
          '</span><span class="jl-frow__n">' + x[1] + '</span></button>';
      }).join('');
    };
    return '<div class="jl-facettes">' +
      '<div class="jl-surtitre">Facettes · sur les ' + S.results.length + ' résultats chargés</div>' +
      '<div class="jl-hist">' + annees.map(function (y) {
        return '<i class="' + (S.facet.an === y[0] ? 'is-on' : '') + '" style="height:' +
          Math.round(100 * y[1] / max) + '%" title="' + y[0] + ' : ' + y[1] + '"></i>';
      }).join('') + '</div>' +
      '<div class="jl-surtitre" data-espace="haut">Années</div>' +
      fr('an', annees.slice().sort(function (a, b) { return b[0].localeCompare(a[0]); }), 5) +
      '<div class="jl-surtitre" data-espace="haut">Famille</div>' + fr('fam', compte(J.FAM), 5) +
      '<div class="jl-surtitre" data-espace="haut">Juridictions</div>' + fr('juri', compte(function (r) { return r.juridiction; })) +
      '<div class="jl-surtitre" data-espace="haut">Source</div>' + fr('src', compte(function (r) { return r.source; })) +
      (Object.keys(S.facet).some(function (k) { return S.facet[k]; })
        ? '<button type="button" class="jl-frow jl-teal" data-facet="reset=">Tout effacer</button>' : '') +
      '<div class="jl-honnetete" data-espace="haut">Ces compteurs portent sur les résultats <b>chargés</b>, ' +
      'pas sur le fonds entier : les vraies facettes attendent la table auxiliaire. ' +
      'Ne pas en tirer de statistique.</div></div>';
  }

  function lierFacettes() {
    $$('#liste [data-facet]').forEach(function (b) {
      b.onclick = function () {
        var p = b.dataset.facet.split('='), k = p[0], v = p.slice(1).join('=');
        if (k === 'reset') S.facet = {};
        else S.facet[k] = S.facet[k] === v ? '' : v;
        renderResults();
      };
    });
  }

  /* ═══════════════ 7. Thésaurus : pastilles retirables une à une ═══════ */

  var expSeq = 0;
  async function montrerExpansion(q) {
    var bar = $('#expBar');
    bar.hidden = true; bar.innerHTML = '';
    if (!q || !S.thes) return;
    var seq = ++expSeq;
    try {
      var r = await fetch(API + '/api/expand?q=' + encodeURIComponent(q) + '&scope=toutes');
      if (!r.ok || seq !== expSeq) return;
      var d = await r.json();
      var trace = d.trace || [], pills = [];
      trace.forEach(function (t) {
        (t.synonyms || []).forEach(function (s) {
          pills.push('<span class="jl-exp__pill" title="' +
            esc('Ajouté pour le terme « ' + t.original + ' »') + '">' + esc(s.toLowerCase()) +
            '<button type="button" data-exp="' + esc(s) + '" title="Retirer ce terme de la recherche">×</button></span>');
        });
      });
      if (!pills.length) return;
      bar.innerHTML = '<span>Recherche élargie aux termes voisins :</span>' + pills.join('') +
        '<a class="jl-exp__off" id="expOff" role="button" tabindex="0">chercher les mots exacts</a>';
      bar.hidden = false;
      $$('#expBar [data-exp]').forEach(function (b) {
        b.onclick = function () { b.parentNode.classList.toggle('is-removed'); };
      });
      $('#expOff').onclick = function () {
        S.thes = false;
        $('#thesT').classList.remove('is-on');
        $('#thesT').setAttribute('aria-pressed', 'false');
        majAvance(); lancer();
      };
    } catch (e) { /* muet : l'expansion est un confort, pas un résultat */ }
  }

  /* ═══════════════ 8. Panneau latéral « article de loi » ═══════════════ */

  var loiCourant = null;

  function ouvrirLoi(code, num, date) {
    loiCourant = { code: code, num: num, date: date || null, data: null };
    $('#loiTitre').textContent = 'Article ' + num;
    $('#loiMeta').textContent = code;
    $('#loiNote').hidden = true;
    $('#loiCorps').innerHTML = '<p class="jl-muted"><span class="jl-spin"></span> Chargement de l’article…</p>';
    document.body.classList.add('jl-loi-ouverte');
    $('#loiPanneau').setAttribute('aria-hidden', 'false');
    resoudreLoi(code, num, date).then(function (d) { rendreLoi(code, num, d); });
  }
  function fermerLoi() {
    document.body.classList.remove('jl-loi-ouverte');
    $('#loiPanneau').setAttribute('aria-hidden', 'true');
  }

  async function resoudreLoi(code, num, date) {
    var c = J.cacheLoiGet(code, num, date);
    if (c) return c;
    try {
      var r = await fetch(API + '/api/law?code=' + encodeURIComponent(code) + '&num=' + encodeURIComponent(num) +
        (date ? '&date=' + encodeURIComponent(date) : ''));
      if (r.ok) { var d = await r.json(); J.cacheLoiSet(code, num, date, d); return d; }
    } catch (e) {}
    return null;
  }

  function rendreLoi(code, num, d) {
    if (!loiCourant) return;
    loiCourant.data = d;
    var ext = $('#loiExtern');
    if (!d || d.error || !d.texte) {
      $('#loiTitre').textContent = 'Article ' + num;
      $('#loiMeta').textContent = code;
      $('#loiNote').hidden = false;
      $('#loiNote').innerHTML = '<b>Introuvable.</b> L’article ' + esc(code + ' ' + num) +
        ' n’est pas résolu par notre base. Ce n’est pas la preuve qu’il n’existe pas : ' +
        'le lien ci-dessous cherche directement sur Légifrance.';
      $('#loiCorps').innerHTML = '';
      ext.href = 'https://www.legifrance.gouv.fr/search/all?query=' +
        encodeURIComponent('article ' + num + ' ' + code);
      return;
    }
    $('#loiTitre').textContent = ('Article ' + (d.num || num) + ' ' + (d.titre_texte || '')).trim();
    var etat = d.etat || '';
    var cls = etat === 'VIGUEUR' ? 'jl-pastille--ok' : (etat === 'ABROGE' ? 'jl-pastille--morte' : 'jl-pastille--q');
    var plage = d.date_debut
      ? 'Rédaction du ' + J.fmtCourt(d.date_debut) +
        (d.date_fin && d.date_fin !== '2999-01-01' ? ' au ' + J.fmtCourt(d.date_fin) : ' — en vigueur')
      : '';
    $('#loiMeta').innerHTML = esc(plage) +
      (etat ? ' <span class="jl-pastille ' + cls + '">' + esc(etat) + '</span>' : '') +
      (loiCourant.date ? ' <span class="jl-provenance" title="Rédaction demandée à la date de la décision lue.">à la date du ' +
        esc(J.fmtCourt(loiCourant.date)) + '</span>' : '');
    if (d.note) { $('#loiNote').hidden = false; $('#loiNote').textContent = d.note; }
    else $('#loiNote').hidden = true;
    /* Un texte d'article arrive souvent en un seul bloc : JL.decouperTexte
       (= splitLegalBlock, search.html:1151-1206) lui rend ses paragraphes. */
    var paras = String(d.texte).indexOf('\n') >= 0
      ? String(d.texte).split(/\n{1,}/).map(function (p) { return p.trim(); }).filter(Boolean)
      : J.decouperTexte(d.texte);
    $('#loiCorps').innerHTML = paras.map(function (p) {
      return '<p>' + J.lierArticles(esc(p)) + '</p>';
    }).join('') + (d.nota ? '<div class="jl-note" data-espace="haut"><b>Nota.</b> ' + esc(d.nota) + '</div>' : '');
    ext.href = d.source_url || (d.legiarti
      ? 'https://www.legifrance.gouv.fr/codes/article_lc/' + encodeURIComponent(d.legiarti)
      : 'https://www.legifrance.gouv.fr/search/all?query=' + encodeURIComponent('article ' + num + ' ' + code));
  }

  async function toutesLesVersions() {
    if (!loiCourant) return;
    var c = $('#loiCorps');
    c.innerHTML = '<p class="jl-muted"><span class="jl-spin"></span> Chargement des rédactions…</p>';
    try {
      var r = await fetch(API + '/api/law/versions?code=' + encodeURIComponent(loiCourant.code) +
        '&num=' + encodeURIComponent(loiCourant.num));
      var d = await r.json();
      var vs = d.versions || [];
      if (!vs.length) { c.innerHTML = '<div class="jl-honnetete">Aucune rédaction de cet article dans LEGI.</div>'; return; }
      c.innerHTML = '<div class="jl-surtitre">Toutes les rédactions (' + vs.length + ')</div>' +
        vs.map(function (v) {
          var cls = v.etat === 'VIGUEUR' ? 'jl-pastille--ok' : (v.etat === 'ABROGE' ? 'jl-pastille--morte' : 'jl-pastille--q');
          return '<div class="jl-loi__v"><div class="jl-muted jl-petit">' +
            esc(J.fmtCourt(v.date_debut)) + ' → ' +
            esc(v.date_fin && v.date_fin !== '2999-01-01' ? J.fmtCourt(v.date_fin) : 'en vigueur') +
            ' <span class="jl-pastille ' + cls + '">' + esc(v.etat || '?') + '</span></div><div>' +
            esc(v.texte || '') + '</div></div>';
        }).join('');
    } catch (e) {
      c.innerHTML = '<div class="jl-alerte"><b>Échec :</b> ' + esc(e.message) + '</div>';
    }
  }

  /* ═══════════════ 9. Flux « Nouveautés » ══════════════════════════════ */

  var flux = { off: 0, busy: false, fini: false, obs: null };
  async function chargerFlux() {
    if (flux.busy || flux.fini) return;
    flux.busy = true;
    var cartes = $('#fluxCartes'), fin = $('#fluxFin');
    cartes.insertAdjacentHTML('beforeend',
      '<div id="skel">' + Array.from({ length: flux.off ? 4 : 6 }, function () {
        return '<div class="jl-sk"><div style="width:30%"></div><div style="width:56%;height:14px"></div>' +
          '<div style="width:88%"></div><div style="width:64%"></div></div>';
      }).join('') + '</div>');
    try {
      var r = await fetch(API + '/api/recent?limit=' + (flux.off ? 12 : 18) + '&offset=' + flux.off);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      var d = await r.json();
      var el = document.getElementById('skel'); if (el) el.remove();
      var rows = d.results || [];
      if (!rows.length) { flux.fini = true; fin.textContent = flux.off ? 'Fin du flux.' : 'Rien à afficher.'; return; }
      cartes.insertAdjacentHTML('beforeend', rows.map(carteFlux).join(''));
      flux.off += rows.length;
      if (rows.length < 12) { flux.fini = true; fin.textContent = 'Fin du flux.'; }
    } catch (e) {
      var s = document.getElementById('skel'); if (s) s.remove();
      flux.fini = true;
      $('#fluxSub').innerHTML = '<span class="jl-warnp">indisponible</span>';
      fin.innerHTML = '<div class="jl-honnetete">Le flux des nouveautés n’a pas répondu (' +
        esc(e.message) + '). Rien n’est affiché plutôt qu’un échantillon qui ferait croire ' +
        'à un état de la base.</div>';
    } finally { flux.busy = false; }
  }
  function carteFlux(r) {
    var fam = J.FAM(r), f = J.fmtFormation(r.formation);
    var txt = String(r.sommaire || r.debut || r.extract || '').replace(/<[^>]*>/g, '');
    return '<a class="jl-flux__carte" href="' + esc(DECISION_BASE + '/' + encodeURIComponent(r.source) +
      '/' + encodeURIComponent(r.id)) + '">' +
      '<div class="jl-flux__haut"><span class="jl-tag jl-tag--' + fam + '">' + esc(J.FAMLABEL[fam]) + '</span>' +
      '<span>' + esc(r.juridiction || '') + (f ? ' · ' + esc(f) : '') + '</span>' +
      (r.sommaire ? '<span class="jl-off">sommaire officiel</span>' : '') +
      '<span class="jl-flux__jour">' + esc(J.fmtCourt(r.date)) + '</span></div>' +
      '<div class="jl-flux__t">' + esc(String(r.title || '').replace(/\b(\d{4}-\d{2}-\d{2})\b/g,
        function (m) { return J.fmtDate(m); }) || 'sans titre') + '</div>' +
      (txt ? '<div class="jl-flux__x">' + esc(J.clipExtract(txt, 260)) + '</div>' : '') + '</a>';
  }

  /* ═══════════════ 10. Démarrage ═══════════════════════════════════════ */

  function ouvrirAvance(on) {
    S.advOpen = on;
    $('#advP').hidden = !on;
    $('#advT').setAttribute('aria-expanded', on ? 'true' : 'false');
    $('#advT').classList.toggle('is-on', on || nbFiltres() > 0);
  }

  function demarrer() {
    J = window.JL; $ = J.$; $$ = J.$$; esc = J.esc;

    $('#hint').innerHTML = 'Ça marche : ' + [
      '04-10.362', 'Cass. 2e civ., 10 sept. 2026, n° 23-20.368', '380374',
      'ECLI:FR:CCASS:2021:C300797', 'trouble anormal de voisinage'
    ].map(function (x) {
      return '<span class="jl-kb" data-q="' + esc(x) + '" role="button" tabindex="0">' + esc(x) + '</span>';
    }).join(' · ');
    $$('#hint .jl-kb').forEach(function (k) {
      k.onclick = function () { $('#q').value = k.dataset.q; lancer(); };
      k.onkeydown = function (e) { if (J.estEntree(e)) { e.preventDefault(); k.click(); } };
    });

    lireUrl();
    majAvance();

    $('#sform').addEventListener('submit', function (e) { e.preventDefault(); lancer(); });
    /* Entrée : vue morte au clavier le 8 septembre 2026 sur search.html, d'où
       l'acceptation de toutes les formes de l'événement (JL.estEntree). */
    $('#q').addEventListener('keydown', function (e) { if (J.estEntree(e)) { e.preventDefault(); lancer(); } });
    $('#advT').onclick = function () { ouvrirAvance($('#advP').hidden); };

    /* Menu de juridiction à DEUX NIVEAUX : un groupe (« Administratif »)
       sélectionne ses trois sous-entrées d'un coup, comme .cs-group de
       search.html:737-742. La sélection reste celle des cases : les deux
       commandes écrivent le même état. */
    $('#juriMenu').addEventListener('jl:pick', function (e) {
      var v = e.detail.value;
      if (!v) S.juri = [];
      else {
        var fam = FAMILLES.filter(function (f) { return f.k === v; })[0];
        if (fam) S.juri = fam.fonds.filter(function (x) { return !x[3]; }).map(function (x) { return x[0]; });
        else S.juri = [v];
      }
      majAvance(); syncUrl();
    });
    $('#advClear').onclick = function () {
      S.juri = []; S.lieu = ''; S.formation = ''; S.dateMin = ''; S.dateMax = ''; S.thes = true;
      $('#dateMin').value = ''; $('#dateMax').value = '';
      $('#thesT').classList.add('is-on'); $('#thesT').setAttribute('aria-pressed', 'true');
      majAvance(); syncUrl();
    };
    $('#thesT').onclick = function () {
      S.thes = !S.thes;
      $('#thesT').classList.toggle('is-on', S.thes);
      $('#thesT').setAttribute('aria-pressed', S.thes ? 'true' : 'false');
      majAvance(); syncUrl();
    };
    $('#dateMin').onchange = function () { S.dateMin = this.value; majAvance(); syncUrl(); };
    $('#dateMax').onchange = function () { S.dateMax = this.value; majAvance(); syncUrl(); };

    /* Article cité → panneau latéral (desktop) ou bottom sheet (mobile) :
       c'est le MÊME panneau, le CSS le fait glisser du bas sous 860 px. */
    document.addEventListener('click', function (e) {
      var sp = e.target.closest && e.target.closest('.lawref[data-num]');
      if (sp) { e.preventDefault(); ouvrirLoi(sp.dataset.code, sp.dataset.num, dateDeLaCarte(sp)); return; }
      var sg = e.target.closest && e.target.closest('[data-signal]');
      if (sg) {
        e.preventDefault();
        ouvrirSignalement({ id: sg.dataset.signal, titre: sg.dataset.titre, url: location.href });
      }
    });
    $('#loiX').onclick = fermerLoi;
    $('#loiVoile').onclick = fermerLoi;
    $('#loiVersions').onclick = toutesLesVersions;
    $('#loiTxt').onclick = function () {
      if (!loiCourant || !loiCourant.data) return;
      var d = loiCourant.data;
      J.telecharger(loiCourant.code + '_' + loiCourant.num,
        'Article ' + (d.num || loiCourant.num) + ' — ' + (d.titre_texte || loiCourant.code) + '\n' +
        (d.date_debut ? 'Rédaction du ' + J.fmtDate(d.date_debut) + '\n' : '') +
        'Source : justicelibre.org (Licence Ouverte 2.0)\n\n' + (d.texte || '') +
        (d.nota ? '\n\nNota. ' + d.nota : '') + '\n');
    };
    $('#loiSignal').onclick = function () {
      ouvrirSignalement({ code: loiCourant && loiCourant.code, num: loiCourant && loiCourant.num,
        titre: $('#loiTitre').textContent, url: location.href });
    };
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { fermerLoi(); fermerSignalement(); }
    });
    $('#signalX').onclick = fermerSignalement;
    $('#signalModale').addEventListener('click', function (e) {
      if (e.target === $('#signalModale')) fermerSignalement();
    });

    /* Impression : le navigateur nomme le PDF avec le <title>. On y met la
       requête, pour que le fichier enregistré soit identifiable
       (search.html:2656-2671, transposé à une page de recherche). */
    var titreSauve = null;
    window.addEventListener('beforeprint', function () {
      majRecapImpression();
      if (!S.q) return;
      titreSauve = document.title;
      document.title = ('Recherche « ' + S.q + ' » · justicelibre.org').slice(0, 120);
    });
    window.addEventListener('afterprint', function () {
      if (titreSauve !== null) { document.title = titreSauve; titreSauve = null; }
    });

    if (S.q) lancer();
    else {
      $('#liste').innerHTML = '';
      chargerFlux();
      flux.obs = new IntersectionObserver(function (es) {
        if (es.some(function (e) { return e.isIntersecting; })) chargerFlux();
      }, { rootMargin: '400px' });
      flux.obs.observe($('#fluxFin'));
    }
  }

  /* La date de la décision dont vient l'extrait : elle détermine la rédaction
     d'époque de l'article. Lue sur la carte, pas devinée. */
  function dateDeLaCarte(span) {
    var art = span.closest('.jl-resultat');
    return art && art.dataset.date ? art.dataset.date : null;
  }

  function ouvrirSignalement(ctx) {
    $('#signalGh').href = J.urlSignalement(ctx);
    $('#signalModale').hidden = false;
  }
  function fermerSignalement() { $('#signalModale').hidden = true; }

  if (window.JL) demarrer();
  else window.addEventListener('DOMContentLoaded', function () {
    if (window.JL) demarrer();
    else setTimeout(demarrer, 0);
  });
})();
