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

  /* ═══════════════ Droit : repérage des articles cités ═════════════════ */

  /* JL.lierArticles — REPRISE TELLE QUELLE de highlightLawRefs()
     (search.html:1246-1414). Seul le nom change : le code, les 22 codes, les
     6 conventions, les règlements, directives, lois, décrets et ordonnances
     sont identiques, marqueur \x00LAWREF\x00 compris.
     ⚠ L'entrée doit DÉJÀ être échappée (esc) : la sortie contient des <span>.
     La classe posée reste `lawref` (search.html:1304) pour que le CSS et les
     écouteurs existants continuent de fonctionner. */
  function lierArticles(escapedHtml) {
    var CODES = [
      { code: 'CESEDA', patterns: ['code de l[\'’]entrée et du séjour des étrangers et du droit d[\'’]asile', 'CESEDA'] },
      { code: 'CGCT',   patterns: ['code général des collectivités territoriales', 'CGCT'] },
      { code: 'CGI',    patterns: ['code général des impôts', 'CGI'] },
      { code: 'CRPA',   patterns: ['code des relations entre le public et l[\'’]administration', 'CRPA'] },
      { code: 'CCH',    patterns: ['code de la construction et de l[\'’]habitation', 'CCH'] },
      { code: 'CPI',    patterns: ['code de la propriété intellectuelle', 'CPI'] },
      { code: 'CASF',   patterns: ['code de l[\'’]action sociale et des familles', 'CASF'] },
      { code: 'CMF',    patterns: ['code monétaire et financier', 'CMF'] },
      { code: 'CSS',    patterns: ['code de la sécurité sociale', 'c\\.\\s*séc\\.\\s*soc\\.', 'CSS'] },
      { code: 'CSP',    patterns: ['code de la santé publique', 'c\\.\\s*santé\\s*publ\\.', 'CSP'] },
      { code: 'CJA',    patterns: ['code de justice administrative', 'CJA'] },
      { code: 'CPC',    patterns: ['code de procédure civile', 'c\\.\\s*pr\\.\\s*civ\\.', 'CPC', 'NCPC'] },
      { code: 'CPP',    patterns: ['code de procédure pénale', 'c\\.\\s*pr\\.\\s*pén\\.', 'CPP'] },
      { code: 'C.cons', patterns: ['code de la consommation', 'c\\.\\s*consom?\\.'] },
      { code: 'C.éduc', patterns: ['code de l[\'’]éducation', 'c\\.\\s*éduc\\.'] },
      { code: 'C.com',  patterns: ['code de commerce', 'c\\.\\s*com\\.'] },
      { code: 'CT',     patterns: ['code du travail', 'c\\.\\s*trav\\.', 'CT'] },
      { code: 'CU',     patterns: ['code de l[\'’]urbanisme', 'c\\.\\s*urb\\.'] },
      { code: 'C.env',  patterns: ['code de l[\'’]environnement', 'c\\.\\s*env\\.'] },
      { code: 'CR',     patterns: ['code rural et de la pêche maritime', 'code rural', 'CRPM'] },
      { code: 'CC',     patterns: ['code civil', 'c\\.\\s*civ\\.', 'CC'] },
      { code: 'CP',     patterns: ['code pénal', 'c\\.\\s*pén\\.', 'CP'] }
    ];
    var CONVENTIONS = [
      { code: 'CEDH',   patterns: ['Convention européenne des droits de l[\'’]homme', 'Conv\\.\\s*EDH', 'CEDH'] },
      { code: 'TFUE',   patterns: ['Traité sur le fonctionnement de l[\'’]Union européenne', 'TFUE'] },
      { code: 'TUE',    patterns: ['Traité sur l[\'’]Union européenne', 'TUE'] },
      { code: 'CDFUE',  patterns: ['Charte des droits fondamentaux de l[\'’]Union européenne', 'CDFUE'] },
      { code: 'DDHC',   patterns: ['Déclaration des droits de l[\'’]homme et du citoyen', 'DDHC'] },
      { code: 'CONST',  patterns: ['Constitution(?:\\s+française)?'] }
    ];
    var ART_NUM = '(?:premier|[LRDA]\\b\\.?\\s*)?\\d+(?:[-.\\s]\\d+)*(?:\\s*§\\s*\\d+)?';
    var ART_PREFIX = '(?:articles?|art\\.?)';
    var ART_ALINEA = '(?:\\s*,?\\s*(?:alinéas?|al\\.)\\s*\\d+)?';
    var ART_FULL = ART_PREFIX + '\\s+' + ART_NUM + ART_ALINEA +
      '(?:\\s*(?:,|et|;)\\s*' + ART_NUM + ART_ALINEA + ')*';
    var ART_LETTER = '[LRDA]\\b\\.?\\s*\\d+(?:[-.\\s]\\d+)*(?:\\s*§\\s*\\d+)?';

    function makeWrap(item, art, code) {
      var numRe = /(?:[LRDA]\b\.?\s*)?\d+(?:[-.]\d+)*(?:\s*§\s*\d+)?/g;
      var matches = [], m;
      while ((m = numRe.exec(art)) !== null) { matches.push(m); if (m.index === numRe.lastIndex) numRe.lastIndex++; }
      var safeCode = item.code;
      if (matches.length <= 1) {
        var num = matches[0] ? matches[0][0].replace(/\s+/g, '') : '';
        return '<span class="lawref" data-code="' + safeCode + '" data-num="' + num +
          '" title="' + safeCode + ' ' + num + '">' + art + ' ' + code + '</span>';
      }
      var html = '', lastEnd = 0;
      for (var i = 0; i < matches.length; i++) {
        var mm = matches[i], n2 = mm[0].replace(/\s+/g, '');
        html += art.substring(lastEnd, mm.index);
        html += '<span class="lawref" data-code="' + safeCode + '" data-num="' + n2 +
          '" title="' + safeCode + ' ' + n2 + '">' + mm[0] + '</span>';
        lastEnd = mm.index + mm[0].length;
      }
      html += art.substring(lastEnd);
      html += ' <span class="lawref lawref-code" data-code="' + safeCode + '" title="' + safeCode + '">' + code + '</span>';
      return html;
    }

    var result = String(escapedHtml == null ? '' : escapedHtml);
    var MARKER = '\x00LAWREF\x00';

    CODES.forEach(function (item) {
      var codeAlts = item.patterns.join('|');
      result = result.replace(new RegExp('(' + ART_FULL + ')\\s+(?:du\\s+|de\\s+la\\s+)?(' + codeAlts + ')\\b', 'gi'),
        function (m, art, code) { return m.indexOf(MARKER) >= 0 ? m : MARKER + makeWrap(item, art, code) + MARKER; });
      result = result.replace(new RegExp('(?<![\\w-])(' + ART_LETTER + ART_ALINEA + ')\\s+(?:du\\s+|de\\s+la\\s+)?(' + codeAlts + ')\\b', 'gi'),
        function (m, art, code) { return m.indexOf(MARKER) >= 0 ? m : MARKER + makeWrap(item, art, code) + MARKER; });
    });
    CONVENTIONS.forEach(function (item) {
      var codeAlts = item.patterns.join('|');
      result = result.replace(new RegExp('(' + ART_FULL + ')\\s+(?:du\\s+|de\\s+la\\s+)?(' + codeAlts + ')\\b', 'gi'),
        function (m, art, code) { return m.indexOf(MARKER) >= 0 ? m : MARKER + makeWrap(item, art, code) + MARKER; });
    });
    result = result.replace(/\b(règlement\s+\(?(?:CE|UE|CEE)\)?\s+(?:n[°º]\s*)?\d+\/\d+)\b/gi, function (m) {
      if (m.indexOf(MARKER) >= 0) return m;
      var num = (m.match(/(\d+\/\d+)/) || [])[1] || '';
      return MARKER + '<span class="lawref" data-code="REG-EU" data-num="' + num + '" title="Règlement UE ' + num + '">' + m + '</span>' + MARKER;
    });
    result = result.replace(/\b(directive\s+(?:\(?(?:CE|UE)\)?\s+)?\d+\/\d+(?:\/(?:CE|UE))?)\b/gi, function (m) {
      if (m.indexOf(MARKER) >= 0) return m;
      var num = (m.match(/\d+\/\d+(?:\/(?:CE|UE))?/) || [])[0] || '';
      return MARKER + '<span class="lawref" data-code="DIR-EU" data-num="' + num + '" title="Directive UE ' + num + '">' + m + '</span>' + MARKER;
    });
    result = result.replace(/\b(loi\s+n[°º]\s*(\d{4}-\d+))\b/gi, function (m, full, num) {
      if (m.indexOf(MARKER) >= 0) return m;
      return MARKER + '<span class="lawref" data-code="LOI" data-num="' + num + '" title="Loi n° ' + num + '">' + full + '</span>' + MARKER;
    });
    result = result.replace(/\b(décret\s+n[°º]\s*(\d{4}-\d+))\b/gi, function (m, full, num) {
      if (m.indexOf(MARKER) >= 0) return m;
      return MARKER + '<span class="lawref" data-code="DECRET" data-num="' + num + '" title="Décret n° ' + num + '">' + full + '</span>' + MARKER;
    });
    result = result.replace(/\b(ordonnance\s+n[°º]\s*(\d{4}-\d+))\b/gi, function (m, full, num) {
      if (m.indexOf(MARKER) >= 0) return m;
      return MARKER + '<span class="lawref" data-code="ORD" data-num="' + num + '" title="Ordonnance n° ' + num + '">' + full + '</span>' + MARKER;
    });
    return result.split(MARKER).join('');
  }

  /* JL.decouperTexte — splitLegalBlock (search.html:1151-1206), repris tel
     quel. Un texte juridique concaténé (les séparateurs ont été perdus à
     l'indexation XML) redevient des paragraphes lisibles. */
  function decouperTexte(text) {
    if (!text) return [];
    var t = String(text).replace(/\s+/g, ' ').trim();
    var tempEl = document.createElement('textarea');
    tempEl.innerHTML = t;
    t = tempEl.value;
    t = t.replace(/_{5,}/g, '\n\n');
    t = t.replace(/\s•\s/g, '\n\n');
    t = t.replace(/\s\*\s\*\s\*\s/g, '\n\n');
    t = t.replace(/\.\s+(?=\d{1,3}\.\s+[A-Za-zÀ-ÖØ-öø-ÿ«])/g, '.\n\n');
    var KEYWORDS = ['PAR CES MOTIFS', 'CASSE ET ANNULE', 'LA COUR', 'REJETTE', 'RENVOIE',
      'Faits et procédure', 'Examen des moyens', 'Examen du moyen',
      'Énoncé du moyen', 'Enoncé du moyen', 'Réponse de la Cour',
      'Portée et conséquences', 'EN FAIT', 'EN DROIT'];
    KEYWORDS.forEach(function (kw) {
      t = t.replace(new RegExp('\\s(?=' + kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b)', 'g'), '\n\n');
    });
    t = t.replace(/\s(?=(?:Sur|Mais sur|Et sur) (?:le|les|ce) (?:premier|second|deuxième|troisième|quatrième|cinquième|sixième|septième|huitième|neuvième|unique) moyen)/gi, '\n\n');
    t = t.replace(/\s(?=(?:DIT QUE|CONDAMNE|ORDONNE|FIXE|DÉBOUTE|DECIDE|DÉCIDE)\b)/g, '\n\n');
    var parts = t.split(/\n{2,}/).filter(function (p) { return p.trim().length > 2; });
    var result = [];
    parts.forEach(function (p) {
      if (p.length <= 1500) { result.push(p.trim()); return; }
      var sub = p.split(/(?:\.)\s+(?=[A-ZÉÈ])/).reduce(function (acc, s) {
        if (!acc.length || acc[acc.length - 1].length + s.length > 800) acc.push(s);
        else acc[acc.length - 1] += ' ' + s;
        return acc;
      }, []);
      result = result.concat(sub.map(function (s) { return s.trim(); }));
    });
    return result.filter(function (p) { return p.length > 2; });
  }

  /* JL.surlignerExtrait — highlightExtract (search.html:1415-1431). */
  function surlignerExtrait(html, q, max) {
    var clean = String(html == null ? '' : html).replace(/;+/g, ' · ').trim();
    var lim = max || 320;
    if (clean.length > lim) clean = clean.slice(0, lim) + '…';
    var hasPrebuiltEm = /<em>/.test(clean);
    var escaped = esc(clean);
    if (hasPrebuiltEm) {
      return escaped.replace(/&lt;em&gt;/g, '<em class="jl-hl">').replace(/&lt;\/em&gt;/g, '</em>');
    }
    if (!q) return escaped;
    var tokens = q.replace(/["*&|]/g, ' ').split(/\s+/).filter(function (t) {
      return t.length > 2 && ['AND', 'OR', 'NOT', 'ET', 'OU', 'SAUF'].indexOf(t.toUpperCase()) < 0;
    });
    if (!tokens.length) return escaped;
    var re = new RegExp('(' + tokens.map(function (t) { return t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }).join('|') + ')', 'gi');
    return escaped.replace(re, '<em class="jl-hl">$1</em>');
  }

  /* JL.sourceOfficielle — officialSourceFromId (search.html:2092-2128), avec
     son refus explicite pour DCE_/DCAA_/DTA_/ORTA_ : la majorité des TA ne
     sont JAMAIS sur Légifrance, donc pas de bouton mensonger (null).
     ⚠ Doit rester en sync avec ssr.py:_official_source_from_pattern(). */
  function sourceOfficielle(id, numero) {
    if (!id) return null;
    if (id.indexOf('CETATEXT') === 0) return { label: 'Légifrance', url: 'https://www.legifrance.gouv.fr/ceta/id/' + id };
    if (id.indexOf('JURITEXT') === 0) return { label: 'Légifrance', url: 'https://www.legifrance.gouv.fr/juri/id/' + id };
    if (id.indexOf('CONSTEXT') === 0) return { label: 'Légifrance', url: 'https://www.legifrance.gouv.fr/cons/id/' + id };
    if (/^[0-9a-f]{24}$/.test(id)) return { label: 'courdecassation.fr (Judilibre)', url: 'https://www.courdecassation.fr/decision/' + id };
    if (id.indexOf('001-') === 0) return { label: 'HUDOC (Cour EDH)', url: 'https://hudoc.echr.coe.int/fre?i=' + id };
    if (id.indexOf('ECLI:EU:') === 0) return { label: 'EUR-Lex (CJUE)', url: 'https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=' + encodeURIComponent(id) };
    if (/^\d{4,5}[A-Z]{2}\d{4}$/.test(id) || id.indexOf('CELEX') >= 0) {
      return { label: 'EUR-Lex (CJUE)', url: 'https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:' + id.replace(/^CELEX:?/, '') };
    }
    if (/^(DCE_|DCAA_|DTA_|ORTA_)/.test(id)) return null;   // refus explicite
    if (id.indexOf('Ariane_Web') >= 0) {
      if (numero && /^\d{3,}/.test(numero)) {
        return { label: 'Légifrance (recherche)', url: 'https://www.legifrance.gouv.fr/search/all?query=' + encodeURIComponent(numero) + '&fonds=cetat' };
      }
      return null;
    }
    if (numero && /^\d{3,}/.test(numero)) {
      return { label: 'Légifrance (recherche)', url: 'https://www.legifrance.gouv.fr/search/all?query=' + encodeURIComponent(numero) };
    }
    return null;
  }

  /* JL.entrelacer — entrelacement des résultats par source en mode
     « pertinence » (search.html:1467-1502). Les scores BM25 de fonds
     différents ne sont pas comparables : on prend le 1er de chaque source,
     puis le 2e… L'ordre devient STABLE d'une recherche à l'autre. */
  var ORDRE_SOURCES = ['dila', 'admin', 'ariane', 'legi', 'cedh', 'cjue', 'doctrine'];
  function entrelacer(results, ordre) {
    var ord = ordre || ORDRE_SOURCES;
    var groupes = {};
    (results || []).forEach(function (r) {
      var s = r.source || '?';
      (groupes[s] = groupes[s] || []).push(r);
    });
    var listes = Object.keys(groupes).sort(function (a, b) {
      var ia = ord.indexOf(a), ib = ord.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    }).map(function (k) { return groupes[k]; });
    var out = [];
    for (var i = 0; ; i++) {
      var ajoute = false;
      for (var j = 0; j < listes.length; j++) {
        if (i < listes[j].length) { out.push(listes[j][i]); ajoute = true; }
      }
      if (!ajoute) break;
    }
    return out;
  }

  /* ═══════════════ Tables de référence partagées ═══════════════════════ */

  /* Filtre par lieu : search.html:958-996, repris tel quel. */
  var INSTANCES = {
    ta: [['TA06', 'Nice'], ['TA13', 'Marseille'], ['TA14', 'Caen'], ['TA20', 'Bastia'],
      ['TA21', 'Dijon'], ['TA25', 'Besançon'], ['TA30', 'Nîmes'], ['TA31', 'Toulouse'],
      ['TA33', 'Bordeaux'], ['TA34', 'Montpellier'], ['TA35', 'Rennes'], ['TA38', 'Grenoble'],
      ['TA44', 'Nantes'], ['TA45', 'Orléans'], ['TA51', 'Châlons-en-Ch.'], ['TA54', 'Nancy'],
      ['TA59', 'Lille'], ['TA63', 'Clermont-Ferrand'], ['TA64', 'Pau'], ['TA67', 'Strasbourg'],
      ['TA69', 'Lyon'], ['TA75', 'Paris'], ['TA76', 'Rouen'], ['TA77', 'Melun'],
      ['TA78', 'Versailles'], ['TA80', 'Amiens'], ['TA83', 'Toulon'], ['TA86', 'Poitiers'],
      ['TA87', 'Limoges'], ['TA93', 'Montreuil'], ['TA95', 'Cergy-Pontoise'],
      ['TA101', 'La Réunion'], ['TA102', 'Martinique'], ['TA103', 'Polynésie fr.'],
      ['TA104', 'Nouvelle-Calédonie'], ['TA105', 'Guadeloupe'], ['TA106', 'Guyane'],
      ['TA107', 'Mayotte'], ['TA108', 'St-Martin'], ['TA109', 'St-Barthélemy']],
    caa: [['CAA13', 'Marseille'], ['CAA31', 'Toulouse'], ['CAA33', 'Bordeaux'],
      ['CAA44', 'Nantes'], ['CAA54', 'Nancy'], ['CAA59', 'Douai'], ['CAA69', 'Lyon'],
      ['CAA75', 'Paris'], ['CAA78', 'Versailles']],
    ca: [['Paris', 'Paris'], ['Versailles', 'Versailles'], ['Lyon', 'Lyon'], ['Rennes', 'Rennes'],
      ['Douai', 'Douai'], ['Angers', 'Angers'], ['Limoges', 'Limoges'], ['Bastia', 'Bastia'],
      ['Basse-Terre', 'Basse-Terre'], ['Aix-en-Provence', 'Aix-en-Provence'],
      ['Montpellier', 'Montpellier'], ['Agen', 'Agen'], ['Toulouse', 'Toulouse'],
      ['Orléans', 'Orléans'], ['Bordeaux', 'Bordeaux'], ['Nîmes', 'Nîmes'],
      ['Saint-Denis', 'St-Denis Réunion'], ['Rouen', 'Rouen'], ['Metz', 'Metz'],
      ['Nancy', 'Nancy'], ['Reims', 'Reims'], ['Besançon', 'Besançon'], ['Dijon', 'Dijon'],
      ['Grenoble', 'Grenoble'], ['Chambéry', 'Chambéry'], ['Poitiers', 'Poitiers'],
      ['Pau', 'Pau'], ['Riom', 'Riom'], ['Bourges', 'Bourges'], ['Amiens', 'Amiens'],
      ['Caen', 'Caen'], ['Colmar', 'Colmar'], ['Fort-de-France', 'Fort-de-France'],
      ['Nouméa', 'Nouméa'], ['Papeete', 'Papeete'], ['Cayenne', 'Cayenne']]
  };

  /* Seule la Cour de cassation est réellement filtrable par chambre : le
     serveur ne sait pas le faire pour les autres (search.html:920-929). */
  var FORMATIONS_FILTRABLES = {
    cass: ['Chambre civile 1', 'Chambre civile 2', 'Chambre civile 3', 'Chambre commerciale',
      'Chambre sociale', 'Chambre criminelle', 'Assemblée plénière', 'Chambre mixte']
  };

  var FORMATION_LABELS = {
    CHAMBRE_SOCIALE: 'Chambre sociale', soc: 'Chambre sociale',
    CHAMBRE_CIVILE_1: '1re chambre civile', civ1: '1re chambre civile',
    CHAMBRE_CIVILE_2: '2e chambre civile', civ2: '2e chambre civile',
    CHAMBRE_CIVILE_3: '3e chambre civile', civ3: '3e chambre civile',
    CHAMBRE_COMMERCIALE: 'Chambre commerciale', comm: 'Chambre commerciale',
    CHAMBRE_CRIMINELLE: 'Chambre criminelle', cr: 'Chambre criminelle',
    ASSEMBLEE_PLENIERE: 'Assemblée plénière', pl: 'Assemblée plénière',
    CHAMBRE_MIXTE: 'Chambre mixte', mi: 'Chambre mixte',
    ORDONNANCE_PREMIER_PRESIDENT: 'Ordonnance du premier président', ordo: 'Ordonnance',
    HFJUD: 'Arrêt', HFDEC: 'Décision', HFCOMOLD: 'Rapport de la Commission',
    JUDG: 'Arrêt', ORDER: 'Ordonnance', OPIN_AG: "Conclusions de l'avocat général"
  };
  function fmtFormation(f) { return FORMATION_LABELS[f] || f || ''; }

  var SOURCE_NAMES = {
    dila: 'DILA', ariane: "Conseil d'État (ArianeWeb)", admin: 'justice administrative',
    cedh: 'Cour EDH', cjue: 'CJUE', doctrine: 'avis et doctrine', legi: 'articles de loi'
  };
  var SRC_BADGES = { ariane: 'ce', admin: 'admin', dila: 'jud', cedh: 'cedh', cjue: 'cjue', doctrine: 'admin', legi: 'admin' };
  var FAM = function (r) {
    if (r.source === 'doctrine') return 'doc';
    if (r.source === 'legi') return 'txt';
    if (r.source === 'cedh' || r.source === 'cjue') return 'eu';
    if (r.source === 'dila') return /constitutionnel/i.test(r.juridiction || '') ? 'ce' : 'jud';
    return 'adm';
  };
  var FAMLABEL = { jud: 'Judiciaire', adm: 'Administratif', ce: 'Constitutionnel', eu: 'Européen', doc: 'Avis & doctrine', txt: 'Texte' };

  /* ═══════════════ Cache localStorage des articles de loi ══════════════ */

  /* Cache 24 h + éviction LRU à 500 entrées (search.html:1780-1813). */
  var LOI_PREFIX = 'law:';
  var LOI_TTL = 24 * 3600 * 1000;
  function _loiCle(code, num, date) { return LOI_PREFIX + code + ':' + num + ':' + (date || 'current'); }
  function cacheLoiGet(code, num, date) {
    return _ls(function () {
      var raw = localStorage.getItem(_loiCle(code, num, date));
      if (!raw) return null;
      var o = JSON.parse(raw);
      if (Date.now() - o.t > LOI_TTL) { localStorage.removeItem(_loiCle(code, num, date)); return null; }
      return o.d;
    }, null);
  }
  function cacheLoiSet(code, num, date, data) {
    _ls(function () {
      var keys = Object.keys(localStorage).filter(function (k) { return k.indexOf(LOI_PREFIX) === 0; });
      if (keys.length >= 500) {
        var entries = keys.map(function (k) {
          try { return [k, JSON.parse(localStorage.getItem(k)).t]; } catch (e) { return [k, 0]; }
        }).sort(function (a, b) { return a[1] - b[1]; });
        for (var i = 0; i < 100 && i < entries.length; i++) localStorage.removeItem(entries[i][0]);
      }
      localStorage.setItem(_loiCle(code, num, date), JSON.stringify({ t: Date.now(), d: data }));
    });
  }

  /* ═══════════════ Signalement et téléchargement ═══════════════════════ */

  /* Ticket GitHub pré-rempli (search.html:2056-2066). Jamais de mailto: en
     clair dans le HTML : l'adresse est assemblée au clic (bindMailR). */
  var GITHUB = 'https://github.com/Dahliyaal/justicelibre';
  function urlSignalement(ctx) {
    ctx = ctx || {};
    var quoi = ctx.titre || ctx.id || (ctx.code ? ctx.code + ' ' + (ctx.num || '') : '') || 'recherche';
    var titre = ('Signalement : ' + quoi).slice(0, 120);
    var corps = 'Élément concerné : ' + (ctx.id || quoi) + '\nPage : ' + (ctx.url || location.href) +
      '\n\nProblème constaté (citation non détectée, texte incorrect, mauvaise version...) :\n';
    return GITHUB + '/issues/new?title=' + encodeURIComponent(titre) + '&body=' + encodeURIComponent(corps);
  }
  function bindMailR(root) {
    if (bindMailR._bound) return;
    bindMailR._bound = true;
    document.addEventListener('click', function (e) {
      var a = e.target.closest && e.target.closest('.jl-mail-r');
      if (!a) return;
      var m = a.dataset.u + '@' + a.dataset.d + '.' + a.dataset.t;
      if (a.getAttribute('href') === '#') { e.preventDefault(); a.href = 'mailto:' + m; a.textContent = m; }
    });
  }

  /* Téléchargement .txt (search.html:1744-1756). */
  function telecharger(nom, texte) {
    var blob = new Blob([texte], { type: 'text/plain;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = String(nom || 'document').replace(/[^\w-]+/g, '_').slice(0, 80) + '.txt';
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 0);
  }

  /* Toutes les formes de la touche Entrée (search.html:2574-2576) : elle
     était morte au clavier sur certains navigateurs. */
  function estEntree(e) { return e.key === 'Enter' || e.key === 'Return' || e.keyCode === 13 || e.which === 13; }

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
    bindMailR(document);

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
    /* Droit + recherche (ajoutés pour web/v2/recherche.html) */
    lierArticles: lierArticles, decouperTexte: decouperTexte,
    surlignerExtrait: surlignerExtrait, sourceOfficielle: sourceOfficielle,
    entrelacer: entrelacer, ORDRE_SOURCES: ORDRE_SOURCES,
    INSTANCES: INSTANCES, FORMATIONS_FILTRABLES: FORMATIONS_FILTRABLES,
    FORMATION_LABELS: FORMATION_LABELS, fmtFormation: fmtFormation,
    SOURCE_NAMES: SOURCE_NAMES, SRC_BADGES: SRC_BADGES, FAM: FAM, FAMLABEL: FAMLABEL,
    cacheLoiGet: cacheLoiGet, cacheLoiSet: cacheLoiSet,
    urlSignalement: urlSignalement, bindMailR: bindMailR, GITHUB: GITHUB,
    telecharger: telecharger, estEntree: estEntree,
    init: init
  };
  global.JL = JL;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);

/* ═══════════════════════════════════════════════════════════════════════════
 * v2 article, 13 sept. — ajout NON INTRUSIF (IIFE séparée : ne modifie aucune
 * ligne de ce qui précède). Composant : popover de date.
 * Cahier des charges : inventaire_composants_13sept.md §2.12.
 * Rapport : scratchpad/audit/v2_article_13sept.md
 * ═══════════════════════════════════════════════════════════════════════════ */
(function (global) {
  'use strict';
  var J = global.JL;
  if (!J) return;

  /* JL.bindDatePop(onPick) — câble TOUT [data-jl-datew] présent dans la page.
     Trois entrées, comme l'exige §2.12 : saisie jj/mm/aaaa, calendrier natif,
     puces « sauter à une rédaction ». onPick reçoit la date ISO choisie.
     Le libellé d'erreur est celui du prototype, au mot près. */
  function bindDatePop(onPick, root) {
    J.$$('[data-jl-datew]', root || document).forEach(function (w) {
      if (w.dataset.bound) return;
      w.dataset.bound = '1';
      var pop = w.querySelector('[data-jl-datepop]');
      var txt = w.querySelector('[data-jl-date-txt]');
      var err = w.querySelector('[data-jl-date-err]');
      var cal = w.querySelector('[data-jl-date-cal]');
      var open = w.querySelector('[data-jl-date-open]');
      if (!pop) return;
      var go = function (d) { if (d && typeof onPick === 'function') onPick(d); };
      var submit = function () {
        var d = J.parseFr(txt ? txt.value.replace(/[.\-\s]/g, '/') : '');
        if (!d) { if (err) err.textContent = 'Date illisible : attendu jj/mm/aaaa'; return; }
        if (err) err.textContent = '';
        go(new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10));
      };
      if (open) open.addEventListener('click', function (e) {
        e.stopPropagation();
        var on = pop.classList.toggle('is-open');
        open.setAttribute('aria-expanded', on ? 'true' : 'false');
        if (on && txt) txt.focus();
      });
      var goBtn = w.querySelector('[data-jl-date-go]');
      if (goBtn) goBtn.addEventListener('click', submit);
      if (txt) txt.addEventListener('keydown', function (e) { if (J.estEntree(e)) { e.preventDefault(); submit(); } });
      if (cal) cal.addEventListener('change', function (e) { go(e.target.value); });
      J.$$('[data-jl-date-chip]', w).forEach(function (c) {
        c.addEventListener('click', function () { go(c.dataset.jlDateChip); });
      });
    });
    if (!bindDatePop._global) {
      bindDatePop._global = true;
      document.addEventListener('click', function (e) {
        if (e.target.closest && e.target.closest('[data-jl-datew]')) return;
        J.$$('[data-jl-datepop].is-open').forEach(function (p) { p.classList.remove('is-open'); });
      });
      document.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape') return;
        J.$$('[data-jl-datepop].is-open').forEach(function (p) { p.classList.remove('is-open'); });
      });
    }
  }

  J.bindDatePop = bindDatePop;
})(window);
