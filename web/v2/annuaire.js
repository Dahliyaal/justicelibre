/**
 * web/v2/annuaire.js — l'annuaire EXISTANT, dans le cadre v2.
 *
 * Décision de la propriétaire : la page de production `web/annuaire.html`
 * reste telle quelle. Cette page-ci ne la remplace pas : elle charge LES MÊMES
 * fichiers et rend LE MÊME tableau, sur les composants du normaliseur.
 *
 * Repris de web/annuaire.html, sans changement de comportement :
 *   loadAll()            annuaire.html:6438-6482  (les 3 JSON, la normalisation)
 *   renderMeta()         annuaire.html:6484-6490
 *   renderCoverage()     annuaire.html:6492-6511  (seuils 30 / 70)
 *   populateCategoryFilter() annuaire.html:6513-6525
 *   currentRows()        annuaire.html:6553-6570
 *   fmtContact/fmtMails  annuaire.html:6576-6591
 *   fmtSignal/openSignalModal annuaire.html:6597-6651 (anti-aspiration)
 *   COLS / rowHTML       annuaire.html:6655-6687
 *   PAGE_SIZE = 1000, « Afficher X de plus » / « all »  annuaire.html:6672-6710
 *   tri au clic          annuaire.html:6740-6746
 *
 * ⛔ En local, /data/*.json n'est PAS servi : on pointe la production, et un
 *    échec de chargement s'affiche comme une PANNE (alerte rouge atténuée),
 *    jamais comme « aucun résultat ».
 * ⛔ La barre de filtrage est la barre LOCALE (jl.css §22), jamais la barre
 *    réseau (§21) : rapport §7.3.
 */
(function () {
  'use strict';

  /* Les JSON ne sont servis qu'en production : en local, on va les chercher là. */
  var DATA = (location.hostname === 'justicelibre.org') ? '' : 'https://justicelibre.org';
  var PAGE_SIZE = 1000;

  var J, $, $$, esc;
  var STATE = { all: [], meta: null, labels: {}, sort: { col: 'nom', dir: 1 } };
  var CURRENT_ROWS = [], RENDERED = 0;

  /* ═══════════════ 1. Chargement (annuaire.html:6438-6482) ═════════════ */

  async function unJson(chemin) {
    var r = await fetch(DATA + chemin, { cache: 'default' });
    if (!r.ok) throw new Error(chemin + ' : HTTP ' + r.status);
    return r.json();
  }

  async function loadAll() {
    var t = await Promise.all([
      unJson('/data/annuaire_juridictions.json'),
      unJson('/data/annuaire_prada.json'),
      unJson('/data/annuaire_meta.json')
    ]);
    var juri = t[0], prada = t[1], meta = t[2];
    STATE.meta = meta;
    STATE.labels = Object.assign({}, juri.type_labels, { prada: 'PRADA' });

    STATE.all = [];
    (juri.rows || []).forEach(function (r) {
      var contact = {};
      if (r.tel) contact.tel = r.tel;
      if (r.site) contact.site = r.site;
      if (r.hierarchie) contact.hierarchie = r.hierarchie;
      if (r.adresse_postale) contact.adresse = r.adresse_postale;
      if (r.source_url) contact.source_url = r.source_url;
      if (r.source_label) contact.source_label = r.source_label;
      if (r.contact_extra) contact.extra = r.contact_extra;
      STATE.all.push({
        kind: 'juri', category: r.type,
        category_label: (juri.type_labels || {})[r.type] || r.type,
        nom: r.nom, sub: '', mails: r.mails || [],
        contact: Object.keys(contact).length ? contact : null,
        id: r.id, source: r.source || 'dila'
      });
    });
    (prada.rows || []).forEach(function (r) {
      STATE.all.push({
        kind: 'prada', category: 'prada', category_label: 'PRADA',
        nom: r.organisme,
        sub: r.prada || '',            /* la personne physique désignée */
        mails: r.courriel ? [r.courriel] : [],
        contact: r.adresse ? { adresse: r.adresse } : null,
        id: r.organisme, source: 'cada'
      });
    });
  }

  /* ═══════════════ 2. Métadonnées et complétude ════════════════════════ */

  function renderMeta() {
    var m = STATE.meta;
    var el = $('#metaDate');
    el.innerHTML = 'Bulk DILA capturé le <strong>' + esc(J.fmtDate(m.sources.dila_dump.downloaded)) +
      '</strong> · Annuaire CADA capturé le <strong>' + esc(J.fmtDate(m.sources.cada_prada.downloaded)) +
      '</strong> · Dernière génération : <strong>' +
      esc(J.fmtDate(String(m.generated_at || '').slice(0, 10))) + '</strong>';
  }

  function renderCoverage() {
    var c = STATE.meta.counts || {};
    var items = [
      ['Juridictions locales (DILA)', c.juridictions_total],
      ['Services centraux (API)', c.api_centraux_total || 0],
      ['PRADA référencés (CADA)', c.prada_total],
      ['Total entités indexées', c.grand_total ||
        ((c.juridictions_total || 0) + (c.api_centraux_total || 0) + (c.prada_total || 0))]
    ];
    $('#stats').innerHTML = items.map(function (i) {
      return '<div class="jl-stat"><span class="jl-stat__n">' + J.nb(i[1] || 0) +
        '</span><span class="jl-stat__l">' + esc(i[0]) + '</span></div>';
    }).join('');

    /* Seuils repris tels quels d'annuaire.html:6507 : < 30 % mauvais,
       < 70 % avertissement, sinon bon. Rouge = mort ; doré = avertissement. */
    var cov = STATE.meta.coverage_by_type || {};
    var rows = Object.keys(cov).map(function (t) {
      var s = cov[t]; return { t: t, label: s.label, total: s.total, with_mail: s.with_mail, rate: s.rate };
    }).sort(function (a, b) { return a.rate - b.rate; });
    $('#coverage').querySelector('tbody').innerHTML = rows.map(function (r) {
      var cls = r.rate < 30 ? 'bad' : (r.rate < 70 ? 'warn' : 'ok');
      return '<tr><td>' + esc(r.label) + '</td><td class="jl-mono">' + J.nb(r.total) +
        '</td><td class="jl-mono">' + J.nb(r.with_mail) + '</td>' +
        '<td class="jl-taux jl-taux--' + cls + '">' + r.rate.toFixed(0) + ' %' +
        '<span class="jl-barre" style="--w:' + r.rate.toFixed(0) + '%"></span></td></tr>';
    }).join('');
  }

  /* ═══════════════ 3. Filtres (barre LOCALE, §22) ══════════════════════ */

  function populateCategoryFilter() {
    var counts = {};
    STATE.all.forEach(function (r) { counts[r.category] = (counts[r.category] || 0) + 1; });
    var juriOrder = ['tgi', 'ti', 'cour_appel', 'ta', 'caa', 'tribunal_commerce', 'prudhommes',
      'te', 'spip', 'cdad', 'mjd', 'ordre_avocats', 'tae', 'vif_tj', 'vif_ca', 'bav'];
    var ordered = juriOrder.filter(function (k) { return counts[k]; }).concat(['prada']);
    var items = [{ k: '', label: 'Toutes les catégories (' + J.nb(STATE.all.length) + ')' }]
      .concat(ordered.map(function (k) {
        return { k: k, label: (STATE.labels[k] || k) + ' (' + J.nb(counts[k] || 0) + ')' };
      }));
    $('#catMenu').querySelector('.jl-menu__panel').innerHTML = items.map(function (it, i) {
      return '<div class="jl-menu__item' + (i === 0 ? ' is-selected' : '') +
        '" data-value="' + esc(it.k) + '" data-label="' + esc(it.label) + '">' + esc(it.label) + '</div>';
    }).join('');
  }

  function currentRows() {
    var q = $('#q').value.trim().toLowerCase();
    var cat = $('#catMenu').dataset.value || '';
    var nomail = $('#fnomail').checked;
    return STATE.all.filter(function (r) {
      if (cat && r.category !== cat) return false;
      if (nomail && r.mails.length) return false;
      if (!q) return true;
      if (r.nom && r.nom.toLowerCase().indexOf(q) >= 0) return true;
      if (r.sub && r.sub.toLowerCase().indexOf(q) >= 0) return true;
      if (r.mails.some(function (m) { return m.toLowerCase().indexOf(q) >= 0; })) return true;
      if (r.contact && JSON.stringify(r.contact).toLowerCase().indexOf(q) >= 0) return true;
      if (r.category_label && r.category_label.toLowerCase().indexOf(q) >= 0) return true;
      return false;
    });
  }

  /* ═══════════════ 4. Cellules (annuaire.html:6576-6603) ═══════════════ */

  function fmtContact(r) {
    if (!r.contact) return '';
    var p = [];
    if (r.contact.tel) p.push('<span class="jl-mono">' + esc(r.contact.tel) + '</span>');
    if (r.contact.site) p.push('<a href="' + esc(r.contact.site) + '" target="_blank" rel="external noopener">site</a>');
    if (r.contact.hierarchie) p.push('<span class="jl-muted">' + esc(r.contact.hierarchie) + '</span>');
    if (r.contact.adresse) p.push(esc(r.contact.adresse).split(' | ').join('<br>'));
    if (r.contact.extra) p.push(esc(r.contact.extra));
    /* La ligne « source : … » est une NOTE DE PROVENANCE (§2.9), pas un badge :
       elle prend .jl-provenance, comme partout ailleurs dans la v2. */
    if (r.contact.source_url) {
      p.push('<a class="jl-provenance" href="' + esc(r.contact.source_url) +
        '" target="_blank" rel="external noopener" title="Document d\'origine d\'où cette coordonnée a été extraite">source : ' +
        esc(r.contact.source_label || 'document') + '</a>');
    }
    return p.join('<br>');
  }

  function fmtMails(r) {
    if (!r.mails.length) return '<span class="jl-nomail">non publié</span>';
    return r.mails.map(function (m) {
      return '<a href="mailto:' + esc(m) + '">' + esc(m) + '</a>';
    }).join('<br>');
  }

  /* Anti-aspiration : le bouton « Signaler » ne contient AUCUN mailto en
     clair, et l'adresse de contact n'est ni dans le HTML, ni dans ce fichier
     en un seul morceau : elle est recomposée au clic par JL.bindMailR, à
     partir des attributs data-u / data-d / data-t de la modale. */
  function fmtSignal(r) {
    if (!r.mails.length) return '';
    return '<button type="button" class="jl-bouton jl-bouton--ghost jl-bouton--sm" data-signal="1"' +
      ' data-nom="' + esc(r.nom) + '" data-cat="' + esc(r.category_label) +
      '" data-mails="' + esc(r.mails.join(', ')) + '">Signaler</button>';
  }

  var COLS = [
    { k: 'category_label', label: 'Catégorie', cls: 'jl-td-cat', fmt: function (v, r) {
      /* AXE 3 : la CATÉGORIE D'ENTITÉ (piège n° 3 : ni backend, ni famille). */
      var src = '';
      if (r.source === 'manuel') src = ' <span class="jl-provenance" title="Source non officielle, documentée">manuel</span>';
      else if (r.source === 'api') src = ' <span class="jl-provenance" title="Source : api-lannuaire.service-public.fr">api</span>';
      return '<span class="jl-badge' + (r.kind === 'prada' ? ' jl-badge--prada' : '') + '">' +
        esc(v) + '</span>' + src;
    } },
    { k: 'nom', label: 'Nom / Organisme', cls: 'jl-td-nom', fmt: function (v, r) {
      return esc(v) + (r.sub ? '<span class="jl-sub">' + esc(r.sub) + '</span>' : '');
    } },
    { k: 'mails', label: 'Adresse électronique', cls: 'jl-td-mail', fmt: function (_, r) { return fmtMails(r); } },
    { k: 'contact', label: 'Contact', cls: 'jl-td-contact', fmt: function (_, r) { return fmtContact(r); }, nosort: true },
    { k: '_action', label: '', cls: 'jl-td-action', fmt: function (_, r) { return fmtSignal(r); }, nosort: true }
  ];

  /* ═══════════════ 5. Rendu du tableau ═════════════════════════════════ */

  function renderHeader() {
    $('#thead').innerHTML = '<tr>' + COLS.map(function (c) {
      if (c.nosort) return '<th>' + esc(c.label) + '</th>';
      var on = STATE.sort.col === c.k;
      return '<th data-sort="' + esc(c.k) + '"' + (on ? ' class="is-sorted"' : '') + '>' +
        esc(c.label) + '<span class="jl-arr">' + (on ? (STATE.sort.dir > 0 ? '▲' : '▼') : '▲▼') + '</span></th>';
    }).join('') + '</tr>';
    $$('#thead th[data-sort]').forEach(function (th) {
      th.onclick = function () {
        var col = th.dataset.sort;
        STATE.sort = { col: col, dir: STATE.sort.col === col ? -STATE.sort.dir : 1 };
        renderTable();
      };
    });
  }

  function rowHTML(r) {
    return '<tr>' + COLS.map(function (c) {
      return '<td class="' + c.cls + '">' + (c.fmt ? c.fmt(r[c.k], r) : esc(r[c.k] == null ? '' : r[c.k])) + '</td>';
    }).join('') + '</tr>';
  }

  /* Pagination à 1000 lignes (annuaire.html:6672) : « ~2 000 rows OK partout,
     5 000 marginal ». Calibrée sur un volume que rien d'autre n'atteint. */
  function moreRow() {
    var rest = CURRENT_ROWS.length - RENDERED;
    if (rest <= 0) return '';
    return '<tr class="jl-more"><td colspan="' + COLS.length + '">+ <strong>' + J.nb(rest) +
      '</strong> autres résultats · <button type="button" class="jl-bouton jl-bouton--ghost jl-bouton--sm" data-action="more">Afficher ' +
      J.nb(Math.min(PAGE_SIZE, rest)) + ' de plus</button> · ou ' +
      '<button type="button" class="jl-bouton jl-bouton--ghost jl-bouton--sm" data-action="all">tout afficher</button></td></tr>';
  }

  function appendPage(count) {
    var slice = CURRENT_ROWS.slice(RENDERED, RENDERED + count);
    var tbody = $('#tbody');
    var m = tbody.querySelector('tr.jl-more'); if (m) m.remove();
    tbody.insertAdjacentHTML('beforeend', slice.map(rowHTML).join(''));
    RENDERED += slice.length;
    var h = moreRow();
    if (h) tbody.insertAdjacentHTML('beforeend', h);
  }

  function renderTable() {
    CURRENT_ROWS = currentRows();
    CURRENT_ROWS.sort(function (a, b) {
      var va = a[STATE.sort.col], vb = b[STATE.sort.col];
      if (Array.isArray(va)) va = va[0] || '';
      if (Array.isArray(vb)) vb = vb[0] || '';
      va = String(va == null ? '' : va).toLowerCase();
      vb = String(vb == null ? '' : vb).toLowerCase();
      return va < vb ? -STATE.sort.dir : va > vb ? STATE.sort.dir : 0;
    });
    $('#count').textContent = J.nb(CURRENT_ROWS.length) + ' / ' + J.nb(STATE.all.length) + ' fiches';
    renderHeader();
    RENDERED = 0;
    var tbody = $('#tbody');
    tbody.innerHTML = '';
    if (!CURRENT_ROWS.length) {
      /* « Aucun résultat POUR CES FILTRES » : le jeu est chargé, donc ce vide
         est une vérité. Un échec de chargement, lui, ne passe jamais par ici. */
      tbody.innerHTML = '<tr class="jl-vide-tr"><td colspan="' + COLS.length +
        '">Aucun résultat pour ces filtres. Les ' + J.nb(STATE.all.length) +
        ' fiches sont bien chargées : c\'est le filtre qui ne rend rien.</td></tr>';
      return;
    }
    appendPage(PAGE_SIZE);
  }

  /* ═══════════════ 6. Signalement ══════════════════════════════════════ */

  function ouvrirSignalement(btn) {
    var nom = btn.dataset.nom, cat = btn.dataset.cat, mails = btn.dataset.mails;
    $('#signalFiche').innerHTML = '<strong>' + esc(nom) + '</strong><span class="jl-sub">' +
      esc(cat) + ' · ' + esc(mails) + '</span>';
    $('#signalGh').href = J.GITHUB + '/issues/new?title=' +
      encodeURIComponent(('Signalement annuaire : ' + nom).slice(0, 120)) + '&body=' +
      encodeURIComponent('Fiche : ' + nom + '\nCatégorie : ' + cat + '\nAdresse(s) : ' + mails +
        '\nPage : ' + location.href +
        '\n\nMotif du signalement (adresse morte, changement, autre) :\n');
    $('#signalModale').hidden = false;
  }

  /* ═══════════════ 7. Démarrage ════════════════════════════════════════ */

  function panne(e) {
    /* ⛔ Une panne de chargement N'EST PAS « aucun résultat ». On le dit, on
       dit où, et on propose de réessayer. */
    $('#alerte').innerHTML = '<div class="jl-alerte jl-alerte--icone" data-espace="haut"><b>⚠</b><div>' +
      '<b>Les données de l\'annuaire n\'ont pas pu être chargées.</b> ' + esc(e.message || String(e)) +
      '. Le tableau ci-dessous est vide parce que le chargement a échoué, <b>pas</b> parce qu\'il ' +
      'n\'y a rien : aucune conclusion ne peut être tirée de ce vide. ' +
      (DATA ? 'Les trois fichiers sont lus sur <code>' + esc(DATA) + '/data/</code> : en local, ils ne sont pas servis par le serveur de développement. ' : '') +
      '<button type="button" class="jl-bouton jl-bouton--ghost jl-bouton--sm" data-retry>Réessayer</button>' +
      '</div></div>';
    $('#tbody').innerHTML = '<tr class="jl-vide-tr"><td colspan="' + COLS.length +
      '">Données non chargées : voir l\'avertissement ci-dessus.</td></tr>';
    $('#count').textContent = '—';
    var b = $('#alerte [data-retry]');
    if (b) b.onclick = init;
  }

  async function init() {
    $('#alerte').innerHTML = '';
    $('#tbody').innerHTML = '<tr class="jl-vide-tr"><td colspan="' + COLS.length +
      '"><span class="jl-spin"></span> Chargement des ' + '3 fichiers de données…</td></tr>';
    try {
      await loadAll();
      renderMeta();
      renderCoverage();
      populateCategoryFilter();
      renderTable();
    } catch (e) {
      panne(e);
    }
  }

  function demarrer() {
    J = window.JL; $ = J.$; $$ = J.$$; esc = J.esc;

    /* En local, les téléchargements aussi pointent la production. */
    if (DATA) {
      $$('.jl-dlrow a[href^="/data/"]').forEach(function (a) {
        a.href = DATA + a.getAttribute('href');
        a.removeAttribute('download');   /* cross-origin : `download` est ignoré */
      });
    }

    $('#q').addEventListener('input', (function () {
      var t; return function () { clearTimeout(t); t = setTimeout(renderTable, 150); };
    })());
    $('#catMenu').addEventListener('jl:pick', renderTable);
    $('#fnomail').addEventListener('change', renderTable);

    $('#tbody').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-action]');
      if (b) {
        var rest = CURRENT_ROWS.length - RENDERED;
        appendPage(b.dataset.action === 'all' ? rest : PAGE_SIZE);
        return;
      }
      var s = e.target.closest('button[data-signal]');
      if (s) { e.preventDefault(); ouvrirSignalement(s); }
    });

    $('#signalX').onclick = function () { $('#signalModale').hidden = true; };
    $('#signalModale').addEventListener('click', function (e) {
      if (e.target === $('#signalModale')) $('#signalModale').hidden = true;
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') $('#signalModale').hidden = true;
    });

    window.addEventListener('beforeprint', function () {
      $('#recapImpression').textContent = 'justicelibre.org · Annuaire des juridictions et PRADA · ' +
        $('#count').textContent + ' · ' + location.href;
    });

    init();
  }

  if (window.JL) demarrer();
  else window.addEventListener('DOMContentLoaded', function () {
    if (window.JL) demarrer(); else setTimeout(demarrer, 0);
  });
})();
