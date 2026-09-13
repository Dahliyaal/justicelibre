/**
 * web/v2/doctrine.js — la rubrique « Avis & doctrine » de la refonte v2.
 *
 * Aucun style ni script en ligne dans doctrine.html : tout est ici, et tous
 * les composants partagés sont dans /styles/jl.css et /jl.js.
 *
 * Repris du prototype web/hub.html (scope `avis`) :
 *   - les tuiles par organisme, alimentées par web/hub_doctrine.json
 *     (hub.html:417-441, `loadHD` / `showDocSrc`) ;
 *   - la recherche `juridiction=doctrine` sur /api/search (hub.html:983) ;
 *   - la restriction au fonds cliqué (hub.html:1049-1051).
 * Lecture d'un document : /api/decision?source=doctrine&id=<id>.
 *
 * ⛔ La fiche à droite du texte n'affiche QUE ce que l'inventaire des champs
 *    du 13 septembre 2026 (§10.5) donne pour disponible : organisme, type,
 *    administration, date, sujet, et l'URL officielle (100 %). Rien d'autre
 *    n'est deviné. Le SENS d'un avis CADA n'est pas un champ : il est écrit
 *    en fin de texte après « --- Sens et motivation --- », et c'est là qu'il
 *    est lu — la fiche le dit.
 * ⛔ Jamais « aucun résultat » quand une source n'a pas répondu.
 */
(function () {
  'use strict';

  var API = (location.hostname === 'justicelibre.org') ? '' : 'https://justicelibre.org';
  var MARQUEUR_SENS = '--- Sens et motivation ---';
  var PAGE = 30;

  var J, $, $$, esc;

  /* Fonds servis par le site. CNIL est déclarée ici parce que le prototype la
     montre (hub.html:856) : elle n'est PAS servie par /api/search, seulement
     par le MCP `search_cnil`. Elle reste donc grisée, jamais cliquable. */
  var CNIL = { k: 'cnil', nom: 'CNIL', total: 26737,
    quoi: 'délibérations et sanctions', soon: 'MCP seulement (search_cnil)' };
  var QUOI = {
    cada: 'avis et conseils 1984-2026 : qui peut obtenir quel document',
    ddd: 'décisions, rappels à la loi, règlements amiables',
    ariane_crp: "conclusions devant le Conseil d'État, servies nulle part ailleurs",
    bofip: "doctrine fiscale de l'administration",
    ctn: 'articles vulgarisés, fiches et glossaire du droit du travail'
  };

  var S = { q: '', src: '', id: '', results: [], srcState: {}, total: 0,
    exact: true, offset: 0, more: false, busy: false, seq: 0, HD: null };

  /* ═══════════════ 1. Adresse partageable ══════════════════════════════ */

  function lireUrl() {
    var p = new URLSearchParams(location.search);
    S.q = p.get('q') || '';
    S.src = p.get('src') || '';
    S.id = p.get('id') || '';
    if (S.q) $('#q').value = S.q;
  }

  function syncUrl() {
    var p = new URLSearchParams();
    if (S.q) p.set('q', S.q);
    if (S.src) p.set('src', S.src);
    if (S.id) p.set('id', S.id);
    var s = p.toString();
    history.replaceState(null, '', location.pathname + (s ? '?' + s : ''));
  }

  /* ═══════════════ 2. Dates ════════════════════════════════════════════ */

  /* ⚠ Piège mesuré (inventaire des champs §10.4) : la CADA date en
     jj/mm/aaaa à la source (« 08/07/2021 ») ; `_norm_doctrine` normalise en
     ISO pour le site, mais le MCP et l'entrepôt servent la forme brute, et
     l'entrepôt dit lui-même que le tri par date est « peu fiable sur ce
     sous-fonds ». La page affiche donc la date en toutes lettres ET rappelle
     la forme d'origine, au lieu de laisser croire à une date normalisée
     partout. */
  function jjmmaaaa(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''));
    return m ? m[3] + '/' + m[2] + '/' + m[1] : '';
  }
  function dateLisible(iso) {
    if (!iso) return '';
    if (/^\d{2}\/\d{2}\/\d{4}$/.test(iso)) return iso;  /* déjà jj/mm/aaaa : servi tel quel */
    return J.fmtDate(iso) || iso;
  }
  function titreProvenanceDate(id, iso) {
    var jj = jjmmaaaa(iso);
    if (String(id || '').indexOf('cada:') === 0 && jj) {
      return 'Date servie en ISO par /api/search (' + iso + '). La CADA l’écrit ' + jj +
        ' à la source : c’est la même date, écrite jj/mm/aaaa.';
    }
    return 'Champ `date` servi par /api/search' + (iso ? ' : ' + iso : '') + '.';
  }

  /* ═══════════════ 3. Le sens d'un avis, lu en fin de texte ════════════ */

  /* Le sens n'existe dans AUCUN champ : la CADA l'écrit à la fin du contenu,
     après « --- Sens et motivation --- » (inventaire §10.5). On le coupe du
     texte et on l'affiche à part, en disant d'où il vient. */
  function extraireSens(texte) {
    var t = String(texte || '');
    var i = t.indexOf(MARQUEUR_SENS);
    if (i < 0) return { texte: t, sens: '', motif: '' };
    var apres = t.slice(i + MARQUEUR_SENS.length).replace(/^\s+/, '');
    var lignes = apres.split(/\n+/);
    return {
      texte: t.slice(0, i).replace(/\s+$/, ''),
      sens: (lignes.shift() || '').trim(),
      motif: lignes.join('\n').trim()
    };
  }

  /* ═══════════════ 4. Les tuiles par fonds ═════════════════════════════ */

  async function chargerFonds() {
    if (S.HD) return S.HD;
    /* hub_doctrine.json est servi par le site lui-même (web/hub_doctrine.json) :
       chemin RELATIF, sinon le serveur local se heurte au CORS de la prod. */
    try {
      var r = await fetch('/hub_doctrine.json');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      S.HD = await r.json();
      S.fondsErr = '';
    } catch (e) {
      /* ⛔ Une panne de chargement des tuiles n'efface pas la recherche : elle
         est DITE, et la barre continue de chercher dans tout le fonds. */
      S.HD = { sources: {} };
      S.fondsErr = e.message || String(e);
    }
    return S.HD;
  }

  function renderTuiles() {
    var srcs = (S.HD && S.HD.sources) || {};
    var ks = Object.keys(srcs);
    var h = ks.map(function (k) {
      var s = srcs[k];
      var on = S.src === k;
      return '<button type="button" class="jl-tuile jl-tuile--survol' + (on ? ' is-on' : '') +
        '" data-src="' + esc(k) + '" aria-pressed="' + (on ? 'true' : 'false') + '">' +
        '<div class="jl-tuile__t"><span class="jl-point"></span>' + esc(s.nom) +
        '<span class="jl-spacer"></span><span class="jl-mono jl-muted jl-petit">' +
        J.nb(s.total || 0) + '</span></div>' +
        '<div class="jl-tuile__s">' + esc(QUOI[k] || '') + '</div></button>';
    }).join('');
    /* CNIL : grise, « bientôt » — gris, jamais rouge. */
    h += '<div class="jl-tuile jl-tuile--bientot" title="' + esc(CNIL.soon) + '">' +
      '<div class="jl-tuile__t">' + esc(CNIL.nom) +
      '<span class="jl-spacer"></span><span class="jl-mono jl-muted jl-petit">' +
      J.nb(CNIL.total) + '</span></div>' +
      '<div class="jl-tuile__s">' + esc(CNIL.quoi) + ' - ' + esc(CNIL.soon) + '</div></div>';
    if (S.fondsErr) {
      h = '<div class="jl-alerte jl-alerte--icone"><b>⚠</b><div>La liste des fonds n\'a pas pu être ' +
        'chargée (<code>/hub_doctrine.json</code> : ' + esc(S.fondsErr) + '). Ce n\'est pas qu\'il n\'y ' +
        'a pas de fonds : la recherche ci-dessus fonctionne et porte sur l\'ensemble du fonds doctrine.' +
        '</div></div>' + h;
    }
    $('#tuiles').innerHTML = h;
    $$('#tuiles [data-src]').forEach(function (b) {
      b.onclick = function () {
        S.src = (S.src === b.dataset.src) ? '' : b.dataset.src;
        syncUrl(); renderTuiles(); renderDerniers();
        if (S.q) lancer(); else renderFiltres();
      };
    });
    renderFiltres();
  }

  function renderFiltres() {
    var s = S.src && S.HD && S.HD.sources[S.src];
    $('#advSum').innerHTML = s
      ? '<button type="button" class="jl-filtre is-on" data-off>Fonds : ' + esc(s.nom) + ' ✕</button>'
      : '';
    var b = $('#advSum [data-off]');
    if (b) b.onclick = function () {
      S.src = ''; syncUrl(); renderTuiles(); renderDerniers(); if (S.q) lancer();
    };
  }

  /* Les 12 derniers documents du fonds cliqué (extrait réel de doctrine.db,
     hub.html:437-439). Ce ne sont PAS des résultats de recherche : la page le
     dit, pour qu'on ne les confonde pas avec une réponse à une requête. */
  function renderDerniers() {
    var box = $('#derniers');
    var s = S.src && S.HD && S.HD.sources[S.src];
    if (!s) { box.innerHTML = ''; return; }
    var types = Object.keys(s.types || {}).map(function (t) {
      return '<span class="jl-chip">' + esc(t) + ' · ' + J.nb(s.types[t]) + '</span>';
    }).join(' ');
    box.innerHTML = '<h2 class="jl-titre jl-titre--nu">' + esc(s.nom) +
      ' <span class="jl-muted jl-petit">· ' + J.nb(s.total) + ' documents</span></h2>' +
      (types ? '<p class="jl-advsum">' + types + '</p>' : '') +
      '<p class="jl-surtitre">Derniers documents entrés en base</p>' +
      '<div class="jl-resultats">' + (s.derniers || []).map(function (d) {
        return '<article class="jl-resultat">' +
          '<div class="jl-resultat__meta">' +
          (d.date ? '<span class="jl-provenance" title="' + esc(titreProvenanceDate(d.id, d.date)) + '">' +
            esc(dateLisible(d.date)) + '</span>' : '<span class="jl-vide">date -</span>') +
          (d.type ? '<span class="jl-tag jl-tag--doc">' + esc(d.type) + '</span>' : '') +
          (d.administration ? '<span>' + esc(d.administration) + '</span>' : '') +
          '</div>' +
          '<h3 class="jl-resultat__t"><a href="?id=' + encodeURIComponent(d.id) + '" data-doc="' +
            esc(d.id) + '">' + esc(d.titre || d.sujet || d.id) + '</a></h3>' +
          (d.extrait ? '<p class="jl-resultat__x">' + esc(d.extrait) + '…</p>' : '') +
          '</article>';
      }).join('') + '</div>' +
      '<p class="jl-provenance" title="web/hub_doctrine.json : extrait réel de doctrine.db, les 12 derniers documents par fonds et les comptes par type. Ce n\'est pas une recherche.">source : hub_doctrine.json, 12 derniers par fonds</p>';
    lierDocs(box);
  }

  /* ═══════════════ 5. Recherche ════════════════════════════════════════ */

  async function lancer(plus) {
    var q = $('#q').value.trim();
    if (!plus) { S.q = q; S.offset = 0; S.results = []; S.total = 0; S.id = ''; }
    syncUrl();
    if (!S.q) {
      S.srcState = {}; renderSources();
      $('#liste').innerHTML = '';
      $('#topline').innerHTML = '';
      $('#avertissements').innerHTML = '';
      montrerFonds(true);
      return;
    }
    if (S.busy) return;
    S.busy = true;
    var seq = ++S.seq;
    montrerFonds(false);
    S.srcState = { 'avis et doctrine': { etat: 'run' } };
    renderSources();
    if (!plus) $('#liste').innerHTML = '<p class="jl-muted" data-espace="haut"><span class="jl-spin"></span> Recherche en cours…</p>';

    var params = new URLSearchParams({ q: S.q, limit: String(PAGE), offset: String(S.offset),
      sources: 'doctrine', juridiction: 'doctrine', timeout: '20' });
    try {
      var r = await fetch(API + '/api/search?' + params);
      var ct = r.headers.get('content-type') || '';
      if (ct.indexOf('json') < 0) throw new Error('HTTP ' + r.status);
      var d = await r.json();
      if (seq !== S.seq) { S.busy = false; return; }
      /* Un 4xx est un REFUS déterministe, pas un délai : on ne le rejoue pas. */
      if (r.status >= 400 && r.status < 500) {
        S.srcState = { 'avis et doctrine': { etat: 'refus', why: d.error || ('HTTP ' + r.status) } };
      } else if (d.error) {
        S.srcState = { 'avis et doctrine': { etat: 'refus', why: d.error } };
      } else {
        var muet = (d.sources_no_result || d.sources_en_echec || []).indexOf('doctrine') >= 0;
        var recus = d.results || [];
        if (muet && !recus.length) {
          S.srcState = { 'avis et doctrine': { etat: 'delai', why: "n'a pas répondu à temps (20 s)" } };
        } else {
          S.srcState = { 'avis et doctrine': { etat: 'ok', n: recus.length } };
        }
        var vus = {};
        S.results.forEach(function (x) { vus[x.id] = 1; });
        recus.forEach(function (x) { if (!vus[x.id]) { vus[x.id] = 1; S.results.push(x); } });
        if (typeof d.total === 'number') { S.total = d.total; S.exact = d.total_exact !== false; }
        S.offset += PAGE;
        S.more = recus.length >= PAGE && S.offset < (S.total || Infinity);
      }
    } catch (e) {
      if (seq === S.seq) S.srcState = { 'avis et doctrine': { etat: 'delai', why: e.message || 'pas de réponse' } };
    }
    S.busy = false;
    renderSources();
    renderResults();
  }

  function renderSources() {
    var ks = Object.keys(S.srcState);
    $('#srcState').innerHTML = ks.map(function (k) {
      var st = S.srcState[k];
      var m = {
        run: ['jl-pastille--loader', 'interrogation en cours'],
        ok: ['jl-pastille--ok', 'a répondu' + (st.n != null ? ' · ' + st.n + ' sur cette page' : '')],
        delai: ['jl-pastille--morte', st.why || "n'a pas répondu à temps"],
        refus: ['jl-pastille--q', 'refus du serveur : ' + (st.why || '')]
      }[st.etat] || ['jl-pastille--q', 'état inconnu'];
      var suff = st.etat === 'delai' ? ' · délai' : st.etat === 'refus' ? ' · refus' : '';
      return '<span class="jl-pastille ' + m[0] + '" title="' + esc(k + ' : ' + m[1]) + '">' +
        esc(k) + esc(suff) + '</span>';
    }).join('');
  }

  /* Restriction au fonds cliqué. hub.html:1051 filtre sur `organisme`, ce qui
     RATE les conclusions : hub_doctrine.json dit « Rapporteurs publics » et
     l'API répond `organisme: "Rapporteur public"`. On filtre donc sur le
     PRÉFIXE de l'identifiant (`cada:`, `ariane_crp:`…), qui est la clé réelle
     du sous-fonds (inventaire §10.1). */
  function duFonds(r) { return !S.src || String(r.id || '').split(':')[0] === S.src; }

  function renderResults() {
    var liste = $('#liste');
    var rows = S.results.filter(duFonds);
    var st = S.srcState['avis et doctrine'] || {};

    var av = '';
    if (st.etat === 'refus') {
      av = '<div class="jl-alerte jl-alerte--icone" data-espace="haut"><b>⚠</b><div>Le fonds ' +
        '<b>avis et doctrine</b> a refusé la requête : ' + esc(st.why || '') +
        '. Ce n\'est pas un délai dépassé : rejouer la même requête donnerait le même refus.</div></div>';
    }
    $('#avertissements').innerHTML = av;

    $('#topline').innerHTML = S.q ? '<div class="jl-topline">' +
      '<span class="jl-serif jl-compte">' + J.nb(rows.length) +
      (rows.length === 1 ? ' résultat chargé' : ' résultats chargés') +
      (S.total > rows.length ? ' <span class="jl-muted jl-petit">sur ' + J.nb(S.total) +
        (S.exact ? '' : ' environ') + ' existants</span>' : '') + '</span>' +
      '<span class="jl-muted jl-petit">fonds interrogé : <b class="jl-teal">doctrine</b>' +
      (S.src ? ' · restreint à ' + esc((S.HD.sources[S.src] || {}).nom || S.src) : '') + '</span>' +
      '</div>' : '';

    if (!S.q) { liste.innerHTML = ''; return; }

    if (!rows.length) {
      if (st.etat === 'run') {
        liste.innerHTML = '<p class="jl-muted" data-espace="haut"><span class="jl-spin"></span> Recherche en cours…</p>';
      } else if (st.etat === 'delai') {
        liste.innerHTML = '<div class="jl-honnetete" data-espace="haut"><b>Recherche incomplète.</b> ' +
          'Le fonds « avis et doctrine » n\'a pas répondu à temps : ce « rien » ne veut pas dire ' +
          'qu\'il n\'y a rien. Aucune conclusion ne peut être tirée de cette absence. ' +
          '<button type="button" class="jl-bouton jl-bouton--ghost jl-bouton--sm" data-relancer>Relancer</button></div>';
        var rb = $('#liste [data-relancer]');
        if (rb) rb.onclick = function () { lancer(); };
      } else if (st.etat === 'refus') {
        liste.innerHTML = '<p class="jl-muted" data-espace="haut">Le fonds a refusé la requête (voir ci-dessus).</p>';
      } else if (S.src && S.results.length) {
        liste.innerHTML = '<p class="jl-muted" data-espace="haut">Rien dans ce fonds pour cette requête, ' +
          'mais ' + J.nb(S.results.length) + ' résultat(s) dans les autres fonds : ' +
          '<button type="button" class="jl-bouton jl-bouton--ghost jl-bouton--sm" data-off2>voir tous les fonds</button></p>';
        var ob = $('#liste [data-off2]');
        if (ob) ob.onclick = function () { S.src = ''; syncUrl(); renderTuiles(); renderResults(); };
      } else {
        liste.innerHTML = '<p class="jl-muted" data-espace="haut">Aucun résultat. Le fonds a répondu : ' +
          'il n\'y a rien pour cette requête. Essayez des mots plus larges.</p>';
      }
      return;
    }

    liste.innerHTML = rows.map(carte).join('') +
      (S.more ? '<div class="jl-plus"><button type="button" class="jl-bouton jl-bouton--cta" id="plusBtn"' +
        (S.busy ? ' disabled' : '') + '>Charger la suite</button>' +
        '<div class="jl-plus__detail">' + J.nb(S.offset) + ' sur ' + J.nb(S.total) +
        (S.exact ? '' : ' environ') + '</div></div>' : '');
    var pb = $('#plusBtn');
    if (pb) pb.onclick = function () { lancer(true); };
    lierDocs(liste);
  }

  function carte(r) {
    var fonds = String(r.id || '').split(':')[0];
    var extrait = J.clipExtract(String(r.extract || '').replace(/\s+/g, ' ').trim(), 420);
    return '<article class="jl-resultat">' +
      '<div class="jl-resultat__meta">' +
        /* AXE 1 : le backend interrogé. Un seul ici, `doctrine`. */
        '<span class="jl-src-badge" title="Fonds interrogé : doctrine (entrepôt JusticeLibre)">doctrine</span>' +
        /* AXE 2 : la famille. Ce ne sont pas des jugements. */
        '<span class="jl-tag jl-tag--doc">Avis &amp; doctrine</span>' +
        (r.organisme ? '<span>' + esc(r.organisme) + '</span>' : '<span class="jl-vide">organisme -</span>') +
        (r.formation ? '<span>' + esc(r.formation) + '</span>' : '') +
        (r.date ? '<span class="jl-provenance" title="' + esc(titreProvenanceDate(r.id, r.date)) + '">' +
          esc(dateLisible(r.date)) + '</span>' : '<span class="jl-vide">date -</span>') +
      '</div>' +
      '<h3 class="jl-resultat__t"><a href="?id=' + encodeURIComponent(r.id) + '" data-doc="' +
        esc(r.id) + '">' + esc(r.title || r.id) + '</a></h3>' +
      (extrait ? '<p class="jl-resultat__x">' + extrait + '</p>' : '') +
      '<div class="jl-resultat__ref">' +
        '<span class="jl-mono">' + esc(r.id) + '</span><span>·</span>' +
        (r.juridiction ? '<span>' + esc(r.juridiction) + '</span><span>·</span>' : '') +
        (r.source_url ? '<a href="' + esc(r.source_url) + '" target="_blank" rel="external noopener nofollow">source officielle ↗</a>'
          : '<span class="jl-vide">pas d\'URL officielle</span>') +
        '<span>·</span><button type="button" class="jl-provenance" data-signal="' + esc(r.id) +
          '" data-titre="' + esc(r.title || '') + '">signaler</button>' +
      '</div></article>';
  }

  /* ═══════════════ 6. Lecture d'un document ════════════════════════════ */

  function lierDocs(root) {
    $$('[data-doc]', root).forEach(function (a) {
      a.onclick = function (e) { e.preventDefault(); ouvrir(a.dataset.doc); };
    });
  }

  function montrerFonds(on) {
    $('#fondsBloc').hidden = !on;
    $('#lecture').hidden = true;
  }

  async function ouvrir(id) {
    S.id = id; syncUrl();
    var box = $('#lecture');
    $('#fondsBloc').hidden = true;
    $('#liste').innerHTML = '';
    box.hidden = false;
    box.innerHTML = '<p class="jl-muted" data-espace="haut"><span class="jl-spin"></span> Chargement du document…</p>';
    window.scrollTo(0, 0);
    var d;
    try {
      var r = await fetch(API + '/api/decision?source=doctrine&id=' + encodeURIComponent(id));
      var ct = r.headers.get('content-type') || '';
      if (ct.indexOf('json') < 0) throw new Error('HTTP ' + r.status);
      d = await r.json();
      if (d.error) throw new Error(d.error);
    } catch (e) {
      box.innerHTML = '<div class="jl-alerte jl-alerte--icone" data-espace="haut"><b>⚠</b><div>' +
        'Ce document n\'a pas pu être chargé : ' + esc(e.message || 'pas de réponse') +
        '. Ce n\'est pas la preuve qu\'il n\'existe pas. ' +
        '<button type="button" class="jl-bouton jl-bouton--ghost jl-bouton--sm" data-retry>Réessayer</button>' +
        ' <button type="button" class="jl-bouton jl-bouton--ghost jl-bouton--sm" data-back>Revenir</button>' +
        '</div></div>';
      var rb = box.querySelector('[data-retry]'); if (rb) rb.onclick = function () { ouvrir(id); };
      var bb = box.querySelector('[data-back]'); if (bb) bb.onclick = fermer;
      return;
    }
    box.innerHTML = rendreDocument(d);
    var back = box.querySelector('[data-back]'); if (back) back.onclick = fermer;
    lierDocs(box);
  }

  function fermer() {
    S.id = ''; syncUrl();
    $('#lecture').hidden = true;
    if (S.q) { montrerFonds(false); renderResults(); }
    else montrerFonds(true);
  }

  /* La fiche ne montre QUE les six champs mesurés disponibles (§10.5), chacun
     avec sa provenance. Un champ vide est marqué vide, jamais comblé. */
  function champ(libelle, valeur, provenance) {
    return '<dt>' + esc(libelle) + '</dt><dd>' +
      (valeur ? esc(valeur) : '<span class="jl-vide">non renseigné</span>') +
      (provenance ? ' <span class="jl-provenance" title="' + esc(provenance) + '">i</span>' : '') +
      '</dd>';
  }

  function rendreDocument(d) {
    var s = extraireSens(d.full_text || '');
    var paras = J.decouperTexte ? J.decouperTexte(s.texte) : String(s.texte || '').split(/\n{2,}/);
    var estCada = String(d.id || '').indexOf('cada:') === 0;

    var fiche = '<aside class="jl-fiche"><h3>La fiche</h3><dl class="jl-dl">' +
      champ('Organisme', d.organisme, "Champ `organisme` servi par /api/decision. Disponible à 100 % sur ce fonds (inventaire des champs §10.2).") +
      champ('Type de document', d.formation, "Champ `formation` de l'API, qui porte le `type` de l'entrepôt (avis, conseil, décision, conclusion…). 100 %.") +
      champ('Administration concernée', d.juridiction, "Champ `juridiction` de l'API, qui porte le champ `administration` de l'entrepôt. 100 %.") +
      '<dt>Date</dt><dd>' + (d.date
        ? esc(dateLisible(d.date)) + ' <span class="jl-provenance" title="' + esc(titreProvenanceDate(d.id, d.date)) + '">' +
          (estCada ? esc(jjmmaaaa(d.date)) : 'i') + '</span>'
        : '<span class="jl-vide">non renseignée</span>') + '</dd>' +
      champ('Sujet', d.sujet, "Champ `sujet`. Taxonomie hiérarchique de la CADA, servie comme une chaîne brute : elle n'est jamais découpée en thème et mots-clés (inventaire §10.3). Mesuré à 87,5 % sur les documents complets.") +
      '<dt>Source officielle</dt><dd>' + (d.source_url
        ? '<a href="' + esc(d.source_url) + '" target="_blank" rel="external noopener nofollow">' +
          esc(d.source_url) + ' ↗</a> <span class="jl-provenance" title="Champ `source_url`, disponible à 100 % sur ce fonds : c\'est le fonds le mieux outillé du site pour le lien officiel (inventaire §10.5).">100 % sur ce fonds</span>'
        : '<span class="jl-vide">non renseignée</span>') + '</dd>' +
      (s.sens ? '<dt>Sens</dt><dd><span class="jl-sens">' + esc(s.sens) + '</span> ' +
        '<span class="jl-provenance" title="Le sens d\'un avis CADA n\'est servi par AUCUN champ de l\'API. Il est écrit à la fin du texte, après « ' + MARQUEUR_SENS + ' ». C\'est là qu\'il a été lu, et il est retiré du corps du texte pour ne pas être pris pour un paragraphe de motivation.">lu en fin de texte</span></dd>' : '') +
      '</dl>' +
      '<p class="jl-honnetete jl-honnetete--nue" data-espace="haut">Ce que cette fiche ne peut pas dire : ' +
      'le numéro d\'affaire du Conseil d\'État derrière une conclusion de rapporteur public (il est dans ' +
      '`tags`, sous la forme <code>AFF:427460</code>, jamais extrait), et le lien vers la décision ' +
      'juridictionnelle qui a suivi l\'avis. Mesuré, pas supposé.</p>' +
      '</aside>';

    return '<p class="jl-fil"><button type="button" class="jl-bouton jl-bouton--ghost jl-bouton--sm" data-back>← Revenir</button></p>' +
      '<div class="jl-kicker">Avis &amp; doctrine</div>' +
      '<h2 class="jl-titre jl-titre--h1">' + esc(d.title || d.id) + '</h2>' +
      '<div class="jl-bande jl-bande--enligne">' +
        '<div><span class="jl-bande__k">Identifiant</span><span class="jl-bande__v jl-mono">' + esc(d.id) + '</span></div>' +
        (d.numero ? '<div><span class="jl-bande__k">Numéro</span><span class="jl-bande__v jl-mono">' + esc(d.numero) + '</span></div>' : '') +
        (d.date ? '<div><span class="jl-bande__k">Date</span><span class="jl-bande__v">' + esc(dateLisible(d.date)) + '</span></div>' : '') +
      '</div>' +
      (s.sens ? '<p class="jl-note">Sens : <span class="jl-sens">' + esc(s.sens) + '</span> ' +
        '<span class="jl-provenance" title="Lu en fin de texte, après « ' + MARQUEUR_SENS + ' ». Ce n\'est pas un champ de l\'API.">lu en fin de texte</span></p>' : '') +
      '<div class="jl-doclec">' +
        '<div class="jl-txt">' +
          (paras.length ? paras.map(function (p) { return '<p>' + esc(p) + '</p>'; }).join('')
            : '<p class="jl-warnp">texte intégral non renvoyé par l\'API pour ce document</p>') +
          (s.motif ? '<h3 class="jl-titre jl-titre--nu">Motivation, telle qu\'elle suit le sens</h3><p>' + esc(s.motif) + '</p>' : '') +
          '<p class="jl-provenance" data-espace="haut" title="Texte servi par /api/decision?source=doctrine. Le champ `text_segments` est toujours vide sur ce fonds : le découpage en paragraphes est fait à l\'affichage, par JL.decouperTexte, et n\'est pas une structure d\'origine.">découpage en paragraphes fait à l\'affichage</p>' +
        '</div>' +
        fiche +
      '</div>';
  }

  /* ═══════════════ 7. Démarrage ════════════════════════════════════════ */

  function ouvrirSignalement(ctx) {
    $('#signalGh').href = J.urlSignalement(ctx);
    $('#signalModale').hidden = false;
  }
  function fermerSignalement() { $('#signalModale').hidden = true; }

  async function demarrer() {
    J = window.JL; $ = J.$; $$ = J.$$; esc = J.esc;

    $('#hint').innerHTML = 'Ça marche : ' + [
      'communication de documents', 'refus de communication dossier médical',
      'discrimination handicap', 'délai de réponse administration',
      'conclusions rapporteur public'
    ].map(function (x) {
      return '<span class="jl-kb" data-q="' + esc(x) + '" role="button" tabindex="0">' + esc(x) + '</span>';
    }).join(' · ');
    $$('#hint .jl-kb').forEach(function (k) {
      k.onclick = function () { $('#q').value = k.dataset.q; lancer(); };
      k.onkeydown = function (e) { if (J.estEntree(e)) { e.preventDefault(); k.click(); } };
    });

    lireUrl();

    $('#sform').addEventListener('submit', function (e) { e.preventDefault(); lancer(); });
    $('#q').addEventListener('keydown', function (e) { if (J.estEntree(e)) { e.preventDefault(); lancer(); } });

    document.addEventListener('click', function (e) {
      var sg = e.target.closest && e.target.closest('[data-signal]');
      if (sg) {
        e.preventDefault();
        ouvrirSignalement({ id: sg.dataset.signal, titre: sg.dataset.titre, url: location.href });
      }
    });
    $('#signalX').onclick = fermerSignalement;
    $('#signalModale').addEventListener('click', function (e) {
      if (e.target === $('#signalModale')) fermerSignalement();
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') fermerSignalement(); });

    window.addEventListener('beforeprint', function () {
      $('#recapImpression').textContent = 'justicelibre.org · Avis & doctrine' +
        (S.q ? ' · recherche « ' + S.q + ' »' : '') +
        (S.src ? ' · fonds ' + S.src : '') + ' · ' + location.href;
    });

    await chargerFonds();
    renderTuiles();
    renderDerniers();
    if (S.id) ouvrir(S.id);
    else if (S.q) lancer();
  }

  if (window.JL) demarrer();
  else window.addEventListener('DOMContentLoaded', function () {
    if (window.JL) demarrer(); else setTimeout(demarrer, 0);
  });
})();
