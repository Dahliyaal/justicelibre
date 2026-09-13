/**
 * jl.js — bibliothèque unique de JusticeLibre (le « normaliseur », volet JS).
 *
 * Cahier des charges : scratchpad/audit/inventaire_composants_13sept.md (§4)
 * Rapport d'exécution : scratchpad/audit/normaliseur_13sept.md
 *
 * Remplace les 15 bascules de thème, les 5 `esc`, les 6 `fmtDate`, les 4
 * `bindCs`, les 4 copies de `$`, de `MOIS`, de `jaccard`, etc. relevées au §4
 * du rapport. Pas de framework, pas de build, ES2018.
 *
 * Le seul autre script partagé est /topbar.js (source unique du header).
 * jl.js ne redéclare PAS le header : il complète topbar.js.
 *
 * ── API EXPOSÉE (window.JL) ────────────────────────────────────────────────
 *  Texte      : esc, clipExtract
 *  Dates      : MOIS, MOISC, fmtDate, fmtCourt, parseFr
 *  Nombres    : nb (formateur), plur (accordeur de pluriel)
 *  DOM        : $, $$, ico, ICO
 *  Thème      : theme(), setTheme(), cycleTheme(), bindTheme()
 *  Mesure     : measureTopbar()
 *  Presse-pap.: copy()
 *  Liaisons   : bindTabs(), bindMenu(), bindToc(), bindPrint(), bindBackLink()
 *  Rendu      : renderRail(), renderSources(), ligneTexte(), pastille(),
 *               noteProvenance()
 */
(function (global) {
  'use strict';

  /* ═══════════════ Texte ═══════════════════════════════════════════════ */

  /* UN SEUL esc. Contrairement aux quatre copies du prototype, il échappe
     AUSSI l'apostrophe : sans cela, une valeur insérée dans un attribut
     title='...' casse le balisage (rapport §4, ligne `esc`). */
  var ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return ESC_MAP[c]; });
  }

  /* Un extrait ne doit pas être une page : ArianeWeb renvoie son analyse
     entière comme extrait. Fenêtre centrée sur le premier <em> surligné. */
  function clipExtract(t, max) {
    if (!t || t.length <= max) return t;
    var i = t.search(/<em>/i), a = 0;
    if (i > max / 2) {
      a = t.lastIndexOf(' ', i - Math.floor(max / 2));
      if (a < 0) a = i - Math.floor(max / 2);
    }
    var b = a + max, sp = t.lastIndexOf(' ', b);
    if (sp > a + max * 0.6) b = sp;
    var out = t.slice(a, b);
    var open = (out.match(/<em>/gi) || []).length, close = (out.match(/<\/em>/gi) || []).length;
    if (open > close) out += '</em>';
    return (a > 0 ? '…' : '') + out + '…';
  }

  /* ═══════════════ Dates ═══════════════════════════════════════════════ */

  var MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
    'août', 'septembre', 'octobre', 'novembre', 'décembre'];
  var MOISC = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.',
    'août', 'sept.', 'oct.', 'nov.', 'déc.'];

  /* UN SEUL fmtDate, convention « 1er » (celle de carte-748 et histo-02 ;
     hub.html:337 écrivait « 1 janvier », c'est la version perdante).
     Accepte YYYY-MM-DD, YYYY-MM-DDTHH:mm:ss et YYYYMMDD. */
  function _parts(iso) {
    if (!iso) return null;
    var s = String(iso);
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s) ||
            /^(\d{4})(\d{2})(\d{2})$/.exec(s);
    return m ? { y: m[1], m: +m[2], d: +m[3] } : null;
  }
  function fmtDate(iso) {
    var p = _parts(iso);
    if (!p) return iso ? String(iso) : '';
    if (p.y === '2999') return 'sans limite';
    return (p.d === 1 ? '1er' : p.d) + ' ' + MOIS[p.m - 1] + ' ' + p.y;
  }
  /* Forme courte, mois abrégés : « 10 sept. 2026 ». */
  function fmtCourt(iso) {
    var p = _parts(iso);
    if (!p) return iso ? String(iso) : '';
    if (p.y === '2999') return 'sans limite';
    return (p.d === 1 ? '1er' : p.d) + ' ' + MOISC[p.m - 1] + ' ' + p.y;
  }
  /* jj/mm/aaaa (saisie humaine) → Date, ou null. */
  function parseFr(s) {
    var m = /^\s*(\d{1,2})\/(\d{1,2})\/(\d{4})\s*$/.exec(String(s || ''));
    if (!m) return null;
    var d = new Date(+m[3], +m[2] - 1, +m[1]);
    if (d.getFullYear() !== +m[3] || d.getMonth() !== +m[2] - 1 || d.getDate() !== +m[1]) return null;
    return d;
  }

  /* ═══════════════ Nombres ═════════════════════════════════════════════ */

  /* PIÈGE N° 2 du rapport : `nb` était un formateur dans hub.html:338 et un
     accordeur de pluriel dans histo-02.html:317. Arbitrage :
       nb   = formateur de nombres
       plur = accordeur de pluriel  */
  function nb(n) { return Number(n).toLocaleString('fr-FR'); }
  function plur(n, un, plusieurs) {
    n = Number(n);
    return nb(n) + ' ' + (Math.abs(n) >= 2 ? (plusieurs || un + 's') : un);
  }
  /* Abrégé : 4300000 → « 4,3 M ». */
  function fmtN(n) {
    n = Number(n);
    if (!isFinite(n)) return '';
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace('.', ',').replace(',0', '') + ' M';
    if (n >= 1e3) return Math.round(n / 1e3) + ' k';
    return nb(n);
  }

  /* ═══════════════ DOM ═════════════════════════════════════════════════ */

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  /* Jeu d'icônes du hub (hub.html:355-366), 13 tracés. */
  var ICO = {
    menu: 'M4 7h16M4 12h16M4 17h16',
    home: 'M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
    scale: 'M12 3v18M5 7h14M7 7l-3 7a3 3 0 0 0 6 0L7 7zm10 0l-3 7a3 3 0 0 0 6 0l-3-7z',
    book: 'M4 4h7a3 3 0 0 1 3 3v13a2 2 0 0 0-2-2H4zM20 4h-7a3 3 0 0 0-3 3v13a2 2 0 0 1 2-2h8z',
    chat: 'M4 5h16v11H8l-4 4z',
    hall: 'M3 21h18M5 21V10M19 21V10M9 21v-6h6v6M12 3l9 6H3z',
    people: 'M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm8 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM2 20a6 6 0 0 1 12 0M14 20a6 6 0 0 1 8 0',
    check: 'M4 12l5 5L20 6',
    bell: 'M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 21h4',
    eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
    diff: 'M4 6h7M4 12h7M4 18h7M13 6h7M13 12h7M13 18h7',
    tree: 'M12 3v6M12 9l-6 4v8M12 9l6 4v8M6 21h0M18 21h0',
    plug: 'M9 2v5M15 2v5M6 7h12v4a6 6 0 0 1-12 0zM12 17v5',
    print: 'M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v7H6z',
    copy: 'M9 9h10v12H9zM5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1',
    cal: 'M4 6h16v15H4zM4 10h16M8 3v4M16 3v4'
  };
  function ico(k, size) {
    var s = size || 18;
    return '<svg width="' + s + '" height="' + s + '" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" ' +
      'stroke-linejoin="round" aria-hidden="true"><path d="' + (ICO[k] || '') + '"/></svg>';
  }

  /* ═══════════════ Thème ═══════════════════════════════════════════════ */

  /* UNE SEULE clé (jl-theme) et UN SEUL cycle : clair → sombre → système.
     La clé « hub-theme » du prototype est reprise une fois puis effacée, pour
     que personne ne perde sa préférence en passant à jl.js. */
  var THEME_KEY = 'jl-theme';
  var THEME_CYCLE = { light: 'dark', dark: 'system', system: 'light' };

  function _ls(fn, dflt) { try { return fn(); } catch (e) { return dflt; } }

  function theme() { return document.documentElement.dataset.theme || 'system'; }

  function setTheme(t) {
    var h = document.documentElement;
    if (t === 'system') {
      delete h.dataset.theme;
      _ls(function () { localStorage.removeItem(THEME_KEY); });
    } else {
      h.dataset.theme = t;
      _ls(function () { localStorage.setItem(THEME_KEY, t); });
    }
    document.dispatchEvent(new CustomEvent('jl:theme', { detail: { theme: t } }));
    return t;
  }

  function cycleTheme() { return setTheme(THEME_CYCLE[theme()] || 'light'); }

  /* Applique la préférence mémorisée. À appeler très tôt (un <script> inline
     en tête de page évite le flash ; cette fonction rattrape le reste). */
  function restoreTheme() {
    var t = _ls(function () { return localStorage.getItem(THEME_KEY); }, null);
    if (!t) {
      var old = _ls(function () { return localStorage.getItem('hub-theme'); }, null);
      if (old === 'light' || old === 'dark') {
        t = old;
        _ls(function () { localStorage.setItem(THEME_KEY, old); localStorage.removeItem('hub-theme'); });
      }
    }
    if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t;
  }

  /* Câble tout élément [data-jl-theme] sur le cycle à trois états. */
  function bindTheme(root) {
    $$('[data-jl-theme]', root).forEach(function (b) {
      if (b.dataset.bound) return;
      b.dataset.bound = '1';
      b.addEventListener('click', function () {
        var t = cycleTheme();
        var lbl = b.querySelector('[data-jl-theme-label]');
        if (lbl) lbl.textContent = { light: 'Thème clair', dark: 'Thème sombre', system: 'Thème : système' }[t];
        b.setAttribute('title', 'Thème : ' + t + ' (clair → sombre → système)');
      });
    });
  }

  /* ═══════════════ Mesure --topbar-h ═══════════════════════════════════ */

  /* UNE SEULE mesure (topbar.js la fait aussi pour ses propres pages ; ici
     c'est le repli pour les pages qui n'ont pas de .topbar, ou dont la
     hauteur change au redimensionnement). */
  function measureTopbar() {
    var el = document.querySelector('.topbar');
    var set = function () {
      var h = el ? el.offsetHeight : 56;
      document.documentElement.style.setProperty('--topbar-h', h + 'px');
    };
    set();
    if (!measureTopbar._bound) {
      measureTopbar._bound = true;
      window.addEventListener('resize', set);
    }
    return set;
  }

  /* ═══════════════ Presse-papier ═══════════════════════════════════════ */

  /* Copie avec REPLI : quand navigator.clipboard manque (http, vieux
     navigateur), on sélectionne le nœud pour que la copie manuelle marche.
     Seules decision-03b/01 avaient ce repli parmi les quatre copies. */
  function copy(text, node) {
    var sel = function () {
      try { if (node) window.getSelection().selectAllChildren(node); } catch (e) {}
    };
    if (global.navigator && navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).catch(function (e) { sel(); throw e; });
    }
    sel();
    return Promise.resolve();
  }

  /* Câble [data-copy="idSource"] ; le retour visuel va dans [data-copy-ok]. */
  function bindCopy(root) {
    $$('[data-copy]', root).forEach(function (btn) {
      if (btn.dataset.bound) return;
      btn.dataset.bound = '1';
      btn.addEventListener('click', function () {
        var el = document.getElementById(btn.dataset.copy);
        if (!el) return;
        var ok = document.querySelector('[data-copy-ok]');
        copy(el.textContent, el).then(function () {
          if (ok) { ok.textContent = 'copié'; setTimeout(function () { ok.textContent = ''; }, 1800); }
        }, function () {
          if (ok) { ok.textContent = 'sélectionné : Ctrl+C'; setTimeout(function () { ok.textContent = ''; }, 2600); }
        });
      });
    });
  }

  /* ═══════════════ Onglets ═════════════════════════════════════════════ */

  /* Les onglets sont en CSS pur (input[type=radio].jl-tab). bindTabs ne fait
     que synchroniser l'ancre : #p8 rouvre l'onglet Texte, #chronologie
     l'onglet Dossier. */
  function bindTabs(map) {
    map = map || { texte: 't-texte', fiche: 't-fiche' };
    function open(id) { var r = document.getElementById(id); if (r) r.checked = true; }
    function fromHash() {
      var h = location.hash.slice(1);
      if (!h) return;
      var el = document.getElementById(h);
      if (!el || !el.closest) return;
      var pane = el.closest('.jl-pane');
      if (!pane) return;
      var k = Array.prototype.slice.call(pane.classList).filter(function (c) {
        return c.indexOf('jl-pane--') === 0;
      })[0];
      if (k) open(map[k.slice(9)]);
      setTimeout(function () { el.scrollIntoView({ block: 'start' }); }, 0);
    }
    window.addEventListener('hashchange', fromHash);
    fromHash();
    $$('input.jl-tab').forEach(function (r) {
      if (r.dataset.bound) return;
      r.dataset.bound = '1';
      r.addEventListener('change', function () {
        history.replaceState(null, '', '#' + r.id.slice(2));
        window.scrollTo(0, 0);
      });
    });
  }

  /* ═══════════════ Menu déroulant ══════════════════════════════════════ */

  /* Fusion des QUATRE bindCs du rapport §2.13 :
       - la molette de stats.html:318-332
       - le garde-fou dataset.bound d'annuaire.html:6530
       - les groupes .cs-group de search.html:198-218
     Appelle onPick(valeur, libellé, élément) et ferme le panneau. */
  function bindMenu(root, onPick) {
    $$('.jl-menu', root || document).forEach(function (wrap) {
      if (wrap.dataset.bound) return;
      wrap.dataset.bound = '1';
      var disp = wrap.querySelector('.jl-menu__display');
      var panel = wrap.querySelector('.jl-menu__panel');
      if (!disp || !panel) return;

      function close() { wrap.classList.remove('is-open'); }
      function items() { return $$('.jl-menu__item, .jl-menu__group', panel); }

      disp.addEventListener('click', function (e) {
        e.stopPropagation();
        var open = wrap.classList.contains('is-open');
        $$('.jl-menu.is-open').forEach(function (w) { w.classList.remove('is-open'); });
        wrap.classList.toggle('is-open', !open);
      });

      panel.addEventListener('click', function (e) {
        var it = e.target.closest('.jl-menu__item, .jl-menu__group');
        if (!it) return;
        items().forEach(function (x) { x.classList.remove('is-selected'); });
        it.classList.add('is-selected');
        var label = (it.dataset.label || it.textContent).trim();
        var value = it.dataset.value != null ? it.dataset.value : label;
        var txt = disp.querySelector('[data-jl-menu-value]');
        if (txt) txt.textContent = label;
        wrap.dataset.value = value;
        close();
        if (typeof onPick === 'function') onPick(value, label, it);
        wrap.dispatchEvent(new CustomEvent('jl:pick', { bubbles: true, detail: { value: value, label: label } }));
      });

      /* Molette : fait défiler la sélection sans ouvrir le panneau. */
      disp.addEventListener('wheel', function (e) {
        if (wrap.classList.contains('is-open')) return;
        var list = $$('.jl-menu__item', panel);
        if (!list.length) return;
        e.preventDefault();
        var cur = list.findIndex(function (x) { return x.classList.contains('is-selected'); });
        var nxt = Math.max(0, Math.min(list.length - 1, (cur < 0 ? 0 : cur) + (e.deltaY > 0 ? 1 : -1)));
        list[nxt].click();
      }, { passive: false });
    });

    if (!bindMenu._global) {
      bindMenu._global = true;
      document.addEventListener('click', function () {
        $$('.jl-menu.is-open').forEach(function (w) { w.classList.remove('is-open'); });
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') $$('.jl-menu.is-open').forEach(function (w) { w.classList.remove('is-open'); });
      });
    }
  }

  /* ═══════════════ Sommaire collant ════════════════════════════════════ */

  function bindToc(tocSel) {
    var toc = $(tocSel || '.jl-toc');
    if (!toc || !('IntersectionObserver' in global)) return;
    var links = $$('a[href^="#"]', toc), map = {};
    links.forEach(function (a) {
      var id = a.getAttribute('href').slice(1), el = document.getElementById(id);
      if (el) map[id] = a;
    });
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        links.forEach(function (a) { a.classList.remove('is-on'); });
        var a = map[e.target.id];
        if (a) a.classList.add('is-on');
      });
    }, { rootMargin: '-20% 0px -70% 0px' });
    Object.keys(map).forEach(function (id) { io.observe(document.getElementById(id)); });
  }

  /* ═══════════════ Impression et retour aux résultats ══════════════════ */

  function bindPrint(sel) {
    $$(sel || '[data-jl-print]').forEach(function (b) {
      if (b.dataset.bound) return;
      b.dataset.bound = '1';
      b.addEventListener('click', function () { window.print(); });
    });
  }

  /* « ← Résultats » n'apparaît QUE si l'on vient bien de la page de recherche. */
  function bindBackLink(rowSel, linkSel) {
    try {
      var r = document.referrer;
      if (!r || !/\/search\.html/.test(r)) return;
      var a = $(linkSel || '#backlink'), row = $(rowSel || '#backrow');
      if (a) a.href = r;
      if (row) row.hidden = false;
    } catch (e) {}
  }

  /* ═══════════════ Rendu : pastille, provenance, ligne-texte ═══════════ */

  /* pastille(état, libellé, pourquoi) — gélule mono à point intégré.
     états : 'ok' (en vigueur) · 'morte' (abrogé) · 'q' (non résolu) ·
             'future' (à venir) · 'loader' (en cours). */
  function pastille(etat, label, why) {
    var cls = 'jl-pastille jl-pastille--' + (etat || 'q');
    return '<span class="' + cls + '"' + (why ? ' title="' + esc(why) + '"' : '') +
      '>' + esc(label || '') + '</span>';
  }

  /* noteProvenance(texte, explication) — bordure POINTILLÉE, cursor:help.
     Dit « d'où je le sais », jamais « attention à cette donnée » (→ .jl-warnp). */
  function noteProvenance(label, tip) {
    return '<span class="jl-provenance"' + (tip ? ' title="' + esc(tip) + '"' : '') +
      '>' + esc(label || '') + '</span>';
  }

  /* ligneTexte({rel, titre, href, long, meta, more, morte}) — les cinq
     registres de la ligne-texte. Les formes pauvres omettent des champs. */
  function ligneTexte(o) {
    o = o || {};
    var h = '<div class="jl-lt' + (o.morte ? ' jl-lt--morte' : '') +
      (o.separee ? ' jl-lt--separee' : '') + '">';
    if (o.rel) h += '<div class="jl-lt__rel">' + esc(o.rel) + '</div>';
    h += '<div class="jl-lt__t">' +
      (o.href ? '<a href="' + esc(o.href) + '">' + esc(o.titre || '') + '</a>' : esc(o.titre || '')) +
      '</div>';
    if (o.long) h += '<div class="jl-lt__long">' + esc(o.long) + '</div>';
    if (o.meta && o.meta.length) h += '<div class="jl-lt__meta">' + o.meta.join(' ') + '</div>';
    if (o.more) h += '<div class="jl-lt__more">' + o.more + '</div>';
    return h + '</div>';
  }

  /* ═══════════════ Rendu du rail « Chercher dans » ═════════════════════ */

  /* Version du hub (la seule qui sache rendre l'état « bientôt » et mémoriser
     le repli). scopes : [{k, icon, label, n, soon}] ; outils : idem. */
  var RAIL_MINI_KEY = 'jl.railMini';

  function renderRail(mount, opts) {
    var el = typeof mount === 'string' ? $(mount) : mount;
    if (!el) return;
    opts = opts || {};
    var mini = opts.mini != null ? opts.mini
      : _ls(function () { return localStorage.getItem(RAIL_MINI_KEY) === '1'; }, false);
    var actif = opts.actif || '';
    var h = '';

    if (opts.repliable !== false) {
      h += '<button class="jl-rail__hd" data-jl-rail-toggle title="Replier / déplier" ' +
        'aria-label="Replier ou déplier le rail">' + ico('menu') +
        '<span class="jl-serif jl-ri__lbl" style="font-size:var(--text-xl);color:var(--teal)">justicelibre</span></button>';
    }
    h += '<div class="jl-rail__sec">Chercher dans</div>';
    (opts.scopes || []).forEach(function (s) {
      h += _railItem(s, actif);
    });
    if (opts.outils && opts.outils.length) {
      h += '<div class="jl-rail__sec">Outils</div>';
      opts.outils.forEach(function (t) { h += _railItem(t, actif); });
    }
    h += '<div class="jl-spacer"></div>';
    var lbl = { light: 'Thème clair', dark: 'Thème sombre', system: 'Thème : système' }[theme()];
    h += '<button class="jl-ri" data-jl-theme title="Clair → sombre → système" ' +
      'style="color:var(--muted);font-size:var(--text-xs)">' +
      '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="8"/>' +
      '<path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" stroke="none"/></svg>' +
      '<span class="jl-ri__lbl" data-jl-theme-label>' + esc(lbl) + '</span></button>';
    h += '<a class="jl-ri" style="color:var(--muted);font-size:var(--text-xs)" ' +
      'href="' + esc(opts.mcp || '/ressources.html') + '">' + ico('plug') +
      '<span class="jl-ri__lbl">API · MCP · GitHub</span></a>';

    el.className = 'jl-rail' + (mini ? ' jl-rail--mini' : '') +
      (opts.cacheMobile ? ' jl-rail--cache' : '');
    el.innerHTML = h;

    bindTheme(el);
    $$('[data-jl-rail-toggle]', el).forEach(function (b) {
      b.addEventListener('click', function () {
        var next = !el.classList.contains('jl-rail--mini');
        _ls(function () { localStorage.setItem(RAIL_MINI_KEY, next ? '1' : '0'); });
        el.classList.toggle('jl-rail--mini', next);
      });
    });
  }

  function _railItem(s, actif) {
    var on = s.k && s.k === actif;
    var soon = !!s.soon;
    var cls = 'jl-ri' + (on ? ' is-on' : '') + (soon ? ' is-soon' : '');
    var tip = soon ? s.label + ' · bientôt' : (s.title || s.label);
    var inner = (s.icon ? ico(s.icon) : '') +
      '<span class="jl-ri__lbl">' + esc(s.label || '') + '</span>' +
      (soon ? '<span class="jl-ri__n">bientôt</span>'
            : (s.n ? '<span class="jl-ri__n">' + esc(s.n) + '</span>' : ''));
    if (soon) {
      return '<button class="' + cls + '" disabled aria-disabled="true" title="' + esc(tip) + '">' +
        inner + '</button>';
    }
    return '<a class="' + cls + '" href="' + esc(s.href || '#') + '" title="' + esc(tip) + '"' +
      (on ? ' aria-current="page"' : '') + '>' + inner + '</a>';
  }

  /* ═══════════════ Rendu des pastilles de source ═══════════════════════ */

  /* sources : [{k, label, etat}] où etat ∈ 'run' | 'ok' | 'ko' | 'soon'.
     ⛔ Ne jamais afficher « aucun résultat » quand une source n'a pas répondu :
     c'est un faux négatif, et sur un site de droit ça fait conclure qu'un
     précédent n'existe pas (motif repris de search.html:1538-1540). */
  function renderSources(mount, sources) {
    var el = typeof mount === 'string' ? $(mount) : mount;
    if (!el) return;
    el.className = 'jl-sources';
    el.innerHTML = (sources || []).map(function (s) {
      var m = {
        run: ['jl-pastille--loader', 'interrogation en cours'],
        ok: ['jl-pastille--ok', 'a répondu'],
        ko: ['jl-pastille--morte', "n'a pas répondu"],
        soon: ['jl-pastille--q', 'pas encore branchée']
      }[s.etat] || ['jl-pastille--q', 'état inconnu'];
      return '<span class="jl-pastille ' + m[0] + '" title="' + esc(s.label + ' : ' + m[1]) + '">' +
        esc(s.label) + (s.n != null ? ' ' + nb(s.n) : '') + '</span>';
    }).join('');
  }

  /* ═══════════════ Copie « pour un LLM » ═══════════════════════════════ */

  /* Assemble un bloc texte structuré à partir du DOM de la page décision :
     référence, ECLI, URL, sommaire officiel, textes visés, texte intégral,
     provenance. Les seules choses qui viennent des DONNÉES de la page (bloc
     JSON #jl-page) sont les URL et la ligne d'identité ; tout le reste est lu
     dans le document, pour qu'aucun texte ne puisse diverger de l'affichage. */
  function bindLLMCopy(btn, d) {
    if (!btn || btn.dataset.bound) return;
    btn.dataset.bound = '1';
    d = d || {};
    var lab = btn.querySelector('[data-jl-llm-label]') || btn;
    function txt(sel) {
      var e = $(sel);
      return e ? e.textContent.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim() : '';
    }
    btn.addEventListener('click', function () {
      var refL = txt('#refL');
      var somm = txt('.jl-somm__t');
      var vises = $$('#textes-vises .jl-vise__t a').map(function (a) {
        return a.textContent.trim() + (d.dateRedaction ? ' (rédaction en vigueur au ' + d.dateRedaction + ') ' : ' ') + a.href;
      }).join('\n');
      var paras = $$('.jl-pane--texte .jl-txt p, .jl-pane--texte .jl-txt h2').map(function (e) {
        if (e.closest('.jl-entete-fold') || e.closest('.jl-somm')) return '';
        return (e.tagName === 'H2' ? '\n## ' : '') + e.textContent.replace(/\s+/g, ' ').trim();
      }).filter(Boolean).join('\n');
      var out = 'DÉCISION DE JUSTICE (source officielle, texte intégral)\n' +
        'Référence : ' + refL + '\n' +
        (d.url ? 'URL : ' + d.url + '\n' : '') +
        (d.sourceUrl ? 'Source officielle : ' + d.sourceUrl + (d.licence ? ' (' + d.licence + ')' : '') + '\n' : '') +
        (d.identite ? d.identite + '\n' : '') +
        (somm ? '\nSOMMAIRE OFFICIEL (rédigé par la Cour, champ DILA « sommaire ») :\n' + somm + '\n' : '') +
        (vises ? '\nTEXTES VISÉS (repérés dans le texte ; pas de visa structuré fourni) :\n' + vises + '\n' : '') +
        '\nTEXTE INTÉGRAL (paragraphes numérotés par la Cour) :\n' + paras + '\n' +
        '\nConsignes pour l’assistant : citer les paragraphes par leur numéro ; ne rien ' +
        'attribuer à cette décision qui ne figure pas dans le texte ci-dessus ; la version ' +
        'qui fait foi est celle de la juridiction.\n';
      var repos = lab.textContent;
      copy(out).then(function () {
        lab.textContent = 'Copié (' + Math.round(out.length / 1000) + ' k car.)';
        setTimeout(function () { lab.textContent = repos; }, 2500);
      }, function () {
        lab.textContent = 'Échec de la copie';
        setTimeout(function () { lab.textContent = repos; }, 2500);
      });
    });
  }

  /* ═══════════════ Démarrage ═══════════════════════════════════════════ */

  /* Données de la page, s'il y en a : <script type="application/json" id="jl-page">.
     C'est le SEUL canal par lequel une page passe ses valeurs à jl.js — aucune
     page n'a besoin de script inline. */
  function pageData() {
    var s = document.getElementById('jl-page');
    if (!s) return {};
    try { return JSON.parse(s.textContent) || {}; } catch (e) { return {}; }
  }

  function init() {
    restoreTheme();
    measureTopbar();
    bindTheme(document);
    bindCopy(document);
    bindPrint();
    bindMenu(document);

    var d = pageData();
    if (d.rail) renderRail('[data-jl-rail]', d.rail);
    if (d.toc !== false) bindToc('.jl-toc');
    if (d.onglets) bindTabs(d.onglets === true ? null : d.onglets);
    if (d.retourRecherche) bindBackLink('#backrow', '#backlink');
    var llm = $('[data-jl-llm]');
    if (llm) bindLLMCopy(llm, d.llm || {});
  }

  var JL = {
    esc: esc, clipExtract: clipExtract,
    MOIS: MOIS, MOISC: MOISC, fmtDate: fmtDate, fmtCourt: fmtCourt, parseFr: parseFr,
    nb: nb, plur: plur, fmtN: fmtN,
    $: $, $$: $$, ICO: ICO, ico: ico,
    theme: theme, setTheme: setTheme, cycleTheme: cycleTheme,
    restoreTheme: restoreTheme, bindTheme: bindTheme, THEME_KEY: THEME_KEY,
    measureTopbar: measureTopbar,
    copy: copy, bindCopy: bindCopy,
    bindTabs: bindTabs, bindMenu: bindMenu, bindToc: bindToc,
    bindPrint: bindPrint, bindBackLink: bindBackLink, bindLLMCopy: bindLLMCopy,
    pageData: pageData,
    renderRail: renderRail, renderSources: renderSources,
    ligneTexte: ligneTexte, pastille: pastille, noteProvenance: noteProvenance,
    init: init
  };
  global.JL = JL;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
