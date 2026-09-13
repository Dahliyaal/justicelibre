/**
 * histo.js — rendu de web/v2/historique.html : les DEUX vues de l'historique
 * d'un article, avec bascule.
 *
 *   Couloirs      — une ligne par texte, le temps en abscisse (histo-02.html)
 *   Poupées russes — accordéons emboîtés, arbre réel (histo-05.html)
 *
 * Modèle : ART.loadHisto() dans article.js (un seul modèle pour les deux vues,
 * comme dans les maquettes). Composants : jl.css §28.7 et §28.8.
 *
 * Les corrections déjà acquises (audit_historique_13sept.md +
 * contre_audit_historique_13sept.md) sont portées telles quelles et ne doivent
 * pas être réintroduites à l'envers : comptes dédupliqués, état recalculé à la
 * date lue, « sera abrogé » au futur, bouchons sur les arrêtés de niveau 1
 * morts, stub « déjà listé plus haut », « réécrit le … » distinct d'un mort.
 */
(function (global) {
  'use strict';
  var J = global.JL, A = global.ART;
  var esc = J.esc, fmtCourt = J.fmtCourt, $ = J.$, $$ = J.$$;

  var H = null;
  var apres = function (d) { return !!d && d > H.at; };
  var futCls = function (d) { return apres(d) ? ' jl-hfutur' : ''; };

  /* Quatre états, quatre rendus. « réécrit » (même NOR, nouvel identifiant)
     n'est PAS un mort : il a sa classe propre (régression R-5 du contre-audit). */
  function clsOf(st) {
    if (st.k === 'ok') return '';
    if (st.k === 'fut') return ' is-fut';
    if (st.k === 'q' && /réécrit/.test(st.label)) return ' is-mod';
    return ' is-dead';
  }

  /* ═══════════════ Diff mot à mot ══════════════════════════════════════ */

  function diffPane(ia, ib) {
    var a = H.redactions[ia], b = H.redactions[ib];
    if (!a || !b || a === b) return '<span class="jl-muted">Même rédaction : rien à comparer.</span>';
    return '<div class="jl-hdiff">' + A.diffWords(a.texte, b.texte) + '</div>';
  }
  function redSelect(id, def) {
    return '<select class="jl-hsel" id="' + id + '" aria-label="rédaction à comparer">' +
      H.redactions.map(function (R, i) {
        return '<option value="' + i + '"' + (i === def ? ' selected' : '') + '>' +
          fmtCourt(R.debut) + ' → ' + fmtCourt(R.fin) + '</option>';
      }).join('') + '</select>';
  }

  /* ═══════════════ VUE 1 · COULOIRS ════════════════════════════════════ */

  /* L'axe commence à la première rédaction de l'article (2008). */
  var Y0 = 2008, Y1 = 2027;
  function gx(iso) {
    if (!iso) return 0;
    var y = +iso.slice(0, 4), m = +iso.slice(5, 7), d = +iso.slice(8, 10);
    var v = (Math.min(Math.max(y, Y0), Y1) + (m - 1) / 12 + d / 365 - Y0) / (Y1 - Y0);
    return Math.max(0, Math.min(100, v * 100));
  }

  function vueCouloirs() {
    var years = []; for (var y = Y0; y <= Y1; y += 2) years.push(y);
    var grid = years.map(function (y) {
      return '<div class="jl-cl__grid" style="left:' + gx(y + '-01-01') + '%"></div>';
    }).join('');
    var atX = gx(H.at);
    var overlay = grid + '<div class="jl-cl__after" style="left:' + atX + '%;right:0"></div>' +
      '<div class="jl-cl__today" style="left:' + atX + '%"></div>';

    /* La ligne de l'article : ses rédactions en segments cliquables. */
    var segs = H.redactions.map(function (R, i) {
      var x = gx(R.debut), w = Math.max(0.8, gx(R.fin) - x);
      var cur = H.cur && R.v === H.cur;
      return '<div class="jl-cl__seg' + (cur ? ' is-cur' : '') + futCls(R.debut) +
        '" role="button" tabindex="0" aria-label="rédaction du ' + fmtCourt(R.debut) +
        ', cliquer pour comparer" data-red="' + i + '" style="left:' + x + '%;width:' + w + '%"' +
        ' title="rédaction du ' + fmtCourt(R.debut) + ' au ' + fmtCourt(R.fin) +
        (cur ? ' · en vigueur à la date lue' : '') + '">' + fmtCourt(R.debut).slice(-4) + '</div>';
    }).join('');

    var rows = '<div class="jl-cl__row jl-cl__row--n0"><div class="jl-cl__name">' +
      '<span class="jl-cl__role">l’article</span>art. ' + esc(H.num) + ' CPC</div>' +
      '<div class="jl-cl__lane">' + overlay + segs + '</div></div>';

    var retRow = function (r, depth) {
      var rx = gx(r.date_texte || r.debut);
      return '<div class="jl-cl__row jl-cl__row--n' + depth + ' jl-cl__row--ret' + futCls(r.date_texte) + '">' +
        '<div class="jl-cl__name" title="' + esc(r.long || r.titre) + '">' +
        '<span class="jl-cl__role" title="' + (r.nature === 'DECRET'
          ? 'Un décret peut modifier un arrêté : il lui est supérieur.' : '') + '">retouché par · ' +
        esc(A.NATLABEL[r.nature] || 'arrêté') + ' modificateur' +
        (r.aussiNiveau1 ? ' · aussi pris pour lui (plus haut)' : '') + '</span>' +
        '<a href="' + r.lf + '">' + esc(r.titre) + '</a></div>' +
        '<div class="jl-cl__lane">' + overlay + '<div class="jl-cl__mark" role="button" tabindex="0" ' +
        'aria-label="retouche du ' + fmtCourt(r.date_texte) + ' par ' + esc(r.titre) + '" ' +
        'data-txt="' + r.id + '" style="left:' + rx + '%" title="' + esc(r.titre) + ' · ' +
        fmtCourt(r.date_texte) + '"></div></div></div>';
    };

    var predRows = function (p, depth) {
      var px = gx(p.debut), pw = Math.max(0.6, gx(p.fin) - px);
      /* Un prédécesseur déjà listé comme arrêté de niveau 1 : on le montre en
         stub, on ne le duplique pas — mais le compte, lui, le comptait (G1-5). */
      if (p.deja) {
        return '<div class="jl-cl__row jl-cl__row--n' + depth + ' is-dead">' +
          '<div class="jl-cl__name" title="' + esc(p.long) + '"><span class="jl-cl__role">remplacé par ' +
          esc(A.minus(p.parent.titre)) + ' · déjà listé plus haut (pris pour lui)</span>' +
          '<a href="' + p.lf + '">' + esc(p.titre) + '</a></div>' +
          '<div class="jl-cl__lane">' + overlay + '</div></div>';
      }
      var cap = p.fin < '2999' ? '<div class="jl-cl__cap" role="button" tabindex="0" aria-label="' +
        (p.fin <= H.at ? 'abrogé' : 'sera abrogé') + ' le ' + fmtCourt(p.fin) + '" style="left:' +
        (px + pw) + '%" title="' + (p.fin <= H.at ? 'abrogé' : 'sera abrogé') + ' le ' + fmtCourt(p.fin) +
        ' · remplacé par ' + esc(p.parent.titre) + '"></div>' : '';
      var pn = p.retouches.map(function (r) {
        return '<div class="jl-cl__notch" role="button" tabindex="0" aria-label="retouché par ' +
          esc(r.titre) + '" style="left:' + gx(r.date_texte || r.debut) + '%" data-txt="' + p.id + '|' +
          r.id + '" title="retouché par ' + esc(r.titre) +
          (r.date_texte ? ' (' + fmtCourt(r.date_texte) + ')' : '') + '"></div>';
      }).join('');
      var h = '<div class="jl-cl__row jl-cl__row--n' + depth + clsOf(p.st) + '">' +
        '<div class="jl-cl__name" title="' + esc(p.long) + '"><span class="jl-cl__role">remplacé par ' +
        esc(A.minus(p.parent.titre)) + (p.retouches.length ? ' · ' + A.acc(p.retouches.length, 'retouche') : '') +
        '</span><a href="' + p.lf + '">' + esc(p.titre) + '</a>' +
        (p.nor ? ' <span class="jl-nor">' + esc(p.nor) + '</span>' : '') + '</div>' +
        '<div class="jl-cl__lane">' + overlay + '<div class="jl-cl__bar jl-cl__bar--n2' + clsOf(p.st) +
        (p.fin >= '2999' ? ' is-inf' : '') + '" data-txt="' + p.id + '" style="left:' + px + '%;width:' +
        pw + '%"></div>' + pn + cap + '</div></div>';
      p.retouches.slice().reverse().forEach(function (r) { h += retRow(r, Math.min(depth + 1, 4)); });
      p.predecesseurs.forEach(function (q) { h += predRows(q, Math.min(depth + 1, 4)); });
      return h;
    };

    /* Ordre antichronologique partout : arrêtés, retouches, prédécesseurs. */
    H.arretes.slice().reverse().forEach(function (a) {
      var x = gx(a.debut), w = Math.max(0.6, gx(a.fin) - x);
      /* Bouchon rouge AUSSI sur les arrêtés de niveau 1 morts (G1-6). */
      var capA = a.fin < '2999' ? '<div class="jl-cl__cap" role="button" tabindex="0" aria-label="' +
        (a.fin <= H.at ? 'abrogé' : 'sera abrogé') + ' le ' + fmtCourt(a.fin) + '" style="left:' + (x + w) +
        '%" title="' + (a.fin <= H.at ? 'abrogé' : 'sera abrogé') + ' le ' + fmtCourt(a.fin) +
        (a.abrogePar ? ' · remplacé par ' + esc(a.abrogePar.titre) : '') + '"></div>' : '';
      var notches = a.retouches.map(function (r) {
        return '<div class="jl-cl__notch" role="button" tabindex="0" aria-label="retouché par ' +
          esc(r.titre) + '" style="left:' + gx(r.date_texte || r.debut) + '%" data-txt="' + a.id + '|' +
          r.id + '" title="retouché par ' + esc(r.titre) +
          (r.date_texte ? ' (' + fmtCourt(r.date_texte) + ')' : '') + '"></div>';
      }).join('');
      rows += '<div class="jl-cl__row jl-cl__row--n1' + clsOf(a.st) + '">' +
        '<div class="jl-cl__name" title="' + esc(a.long) + '"><span class="jl-cl__role">pris pour lui · visa' +
        (a.retouches.length ? ' · ' + A.acc(a.retouches.length, 'retouche') : '') + '</span>' +
        '<a href="' + a.lf + '">' + esc(a.titre) + '</a></div>' +
        '<div class="jl-cl__lane">' + overlay + '<div class="jl-cl__bar' + clsOf(a.st) +
        (a.fin >= '2999' ? ' is-inf' : '') + '" data-txt="' + a.id + '" style="left:' + x + '%;width:' +
        w + '%"></div>' + notches + capA + '</div></div>';
      a.retouches.slice().reverse().forEach(function (r) { rows += retRow(r, 2); });
      a.predecesseurs.forEach(function (p) { rows += predRows(p, 2); });
    });

    return '<div class="jl-hbar"><span class="jl-surtitre">Couloirs</span>' +
      '<span class="jl-muted jl-sub jl-sub--enligne">Chaque texte occupe une ligne, de sa naissance ' +
      'à sa mort. Les losanges ambre sont ses retouches (chacune a aussi sa ligne), le bouchon rouge ' +
      'marque l’abrogation (survole-le : par qui), la pointe à droite signifie « sans limite ». ' +
      'L’axe commence à la première rédaction de l’article (2008) ; le décret qui l’a créé date du ' +
      '28 décembre 2005. Survole pour le détail, clique une rédaction pour la comparer.</span>' +
      '<span class="jl-hcount">' + A.acc(H.counts.total, 'événement') + '</span></div>' +
      '<div class="jl-cl"><div class="jl-cl__in">' +
        '<div class="jl-cl__head"><div class="jl-cl__lbl">texte</div><div class="jl-cl__axis">' +
        years.map(function (y) {
          return '<div class="jl-cl__yr" style="left:' + gx(y + '-01-01') + '%">' + y + '</div>';
        }).join('') +
        '<div class="jl-cl__todayl" style="left:calc(' + atX + '% + 4px)">' +
        (H.isToday ? 'aujourd’hui' : 'date lue') + '</div></div></div>' + rows + '</div></div>' +
      '<div class="jl-cl__tip jl-carte" id="cl-tip" aria-live="polite"><span class="jl-muted">' +
      'Survole (ou tabule jusqu’à) une barre, une encoche ou un segment.</span></div>' +
      '<div class="jl-carte" data-espace="haut">' +
        '<div class="jl-h2">Deux rédactions, mot à mot</div>' +
        '<div class="jl-hbar">' + redSelect('clA', Math.max(0, H.redactions.length - 2)) +
        '<span class="jl-muted">vers</span>' + redSelect('clB', H.redactions.length - 1) + '</div>' +
        '<div id="cl-out"></div></div>';
  }

  function wireCouloirs() {
    var byId = {}; H.textes.forEach(function (t) { byId[t.id] = t; });
    var tip = $('#cl-tip');
    var show = function (t) {
      tip.innerHTML = '<div class="jl-lt__t"><a href="' + t.lf + '">' + esc(t.titre) + '</a></div>' +
        '<div class="jl-lt__long">' + esc(t.long) + '</div>' +
        '<div class="jl-lt__meta">' + (t.nor ? '<span class="jl-nor">' + esc(t.nor) + '</span>' : '') +
        (t.date_texte ? '<span>signé le ' + fmtCourt(t.date_texte) + '</span>' : '') +
        '<span>en vigueur du ' + fmtCourt(t.debut) + ' au ' + fmtCourt(t.fin) + '</span>' +
        A.pill(t.st) + A.howHTML(t.niveau === 1 ? 'visa' : 'succession') +
        '<span>' + A.acc(t.nb_articles, 'article') + '</span></div>';
    };
    $$('[data-txt]').forEach(function (el) {
      var f = function () {
        var ids = el.dataset.txt.split('|');
        var t = byId[ids[ids.length - 1]];
        if (t) show(t);
      };
      el.addEventListener('mouseenter', f);
      el.addEventListener('focus', f);   /* accessible au clavier (G3-3) */
    });

    var pick = [+$('#clA').value, +$('#clB').value];
    var redo = function () {
      var a = +$('#clA').value, b = +$('#clB').value;
      pick = [a, b];
      $('#cl-out').innerHTML = diffPane(a, b);
      $$('.jl-cl__seg').forEach(function (s) {
        s.classList.toggle('is-sel', +s.dataset.red === a || +s.dataset.red === b);
      });
    };
    $$('.jl-cl__seg').forEach(function (s) {
      var choisir = function () {
        var i = +s.dataset.red;
        if (pick.indexOf(i) >= 0) {
          if (pick.length > 1) pick = pick.filter(function (x) { return x !== i; });
          else return;
        } else { pick.push(i); if (pick.length > 2) pick.shift(); }
        if (pick.length === 1) { $('#clA').value = pick[0]; $('#clB').value = pick[0]; redo(); return; }
        var s2 = pick.slice().sort(function (x, y) { return x - y; });
        $('#clA').value = s2[0]; $('#clB').value = s2[1]; redo();
      };
      s.addEventListener('click', choisir);
      s.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choisir(); } });
      var apercu = function () {
        var R = H.redactions[+s.dataset.red];
        tip.innerHTML = '<div class="jl-lt__t">Rédaction du ' + fmtCourt(R.debut) + ' au ' + fmtCourt(R.fin) + '</div>' +
          '<div class="jl-lt__meta"><span class="jl-mono">' + esc(R.legiarti) + '</span>' +
          (R.auteur ? '<span class="jl-lt__rel">' + (R.type === 'cree' ? 'créée par' : 'écrite par') +
            '</span> <a href="' + R.auteur.lf + '">' + esc(R.auteur.titre) + '</a>' : '') +
          A.howHTML('lien LEGI') + '</div>' +
          '<div class="jl-lt__long">' + esc(R.texte.slice(0, 220)) + '…</div>';
      };
      s.addEventListener('mouseenter', apercu);
      s.addEventListener('focus', apercu);
    });
    $('#clA').addEventListener('change', redo);
    $('#clB').addEventListener('change', redo);
    redo();
  }

  /* ═══════════════ VUE 2 · POUPÉES RUSSES ══════════════════════════════ */

  var CHEV = '<svg class="jl-pr__chev" width="12" height="12" viewBox="0 0 24 24" fill="none" ' +
    'stroke="currentColor" stroke-width="3" aria-hidden="true"><path d="M9 5l7 7-7 7"/></svg>';

  function vuePoupees() {
    var friseArt = '<div class="jl-pr__frise">' + H.redactions.map(function (R, i) {
      var cur = !!(H.cur && R.v === H.cur);
      return (i ? '<span class="jl-pr__lnk"></span>' : '') +
        '<span class="jl-pr__seg' + (cur ? ' is-cur' : '') + futCls(R.debut) + '">' +
        '<i class="jl-point jl-point--art"></i>' + fmtCourt(R.debut) + '</span>';
    }).join('') + '</div>';

    var redBlocks = H.redactions.map(function (R, i) {
      var cur = !!(H.cur && R.v === H.cur);
      return '<div class="jl-pr__acc jl-pr__red' + (cur ? ' is-cur' : '') + futCls(R.debut) + '" data-acc>' +
        '<button type="button" class="jl-pr__h">' + CHEV +
        '<span class="jl-pr__ttl">Rédaction du ' + fmtCourt(R.debut) +
        ' <span class="jl-muted jl-poids-normal">au ' + fmtCourt(R.fin) + '</span></span>' +
        '<span class="jl-pr__cnt">' + (R.type === 'cree' ? 'création' : 'réécriture') +
        (R.sim !== null ? ' · ' + Math.round(R.sim * 100) + ' % communs' : '') + '</span></button>' +
        '<div class="jl-pr__body"><div class="jl-lt__meta">' +
        (R.auteur
          ? '<span class="jl-lt__rel">' + (R.type === 'cree' ? 'créée par' : 'écrite par') + '</span> ' +
            '<a href="' + R.auteur.lf + '">' + esc(R.auteur.titre) + '</a>' +
            (R.auteur.art ? ' <span class="jl-muted">art. ' + esc(R.auteur.art) + '</span>' : '') +
            (R.auteur.nor ? '<span class="jl-nor">' + esc(R.auteur.nor) + '</span>' : '')
          : '<span class="jl-muted">aucun texte modificateur relié dans LEGI</span>') +
        A.howHTML('lien LEGI') + '<span class="jl-mono">' + esc(R.legiarti) + '</span></div>' +
        '<div class="jl-htext">' + A.linkArts(A.linkArtsLEGI(esc(R.texte), R.v.liens), 'CPC') + '</div>' +
        (R.nota ? '<div class="jl-nota"><b>Nota.</b> ' + esc(R.nota) + '</div>' : '') +
        (i ? '<div class="jl-pr__in"><div class="jl-h2">Ce qui a changé depuis le ' +
              fmtCourt(H.redactions[i - 1].debut) + '</div>' + diffPane(i - 1, i) + '</div>'
           : '<div class="jl-pr__foot">Première rédaction : rien à comparer.</div>') +
        '</div></div>';
    }).join('');

    var retsHTML = function (o) {
      if (!o.retouches.length) return '<div class="jl-pr__foot" data-espace="haut">Jamais retouché.</div>';
      return '<div class="jl-h2" data-espace="haut">Ses retouches <span class="jl-hcount">' +
        o.retouches.length + '</span></div>' +
        o.retouches.slice().reverse().map(function (r) {
          return '<div class="jl-pr__ret' + futCls(r.date_texte) + '" data-r="' + r.id + '">' +
            '<div class="jl-lt__t"><span class="jl-mono jl-muted jl-pr__dt">' +
            fmtCourt(r.date_texte) + '</span><a href="' + r.lf + '">' + esc(r.titre) + '</a> ' +
            '<span class="jl-muted" title="' + (r.nature === 'DECRET'
              ? 'Un décret peut modifier un arrêté : il lui est supérieur.' : '') + '">' +
            esc(A.NATLABEL[r.nature] || 'arrêté') + ' modificateur' +
            (r.aussiNiveau1 ? ' · aussi pris pour lui (plus haut)' : '') + '</span></div>' +
            '<div class="jl-lt__meta">' + (r.nor ? '<span class="jl-nor">' + esc(r.nor) + '</span>' : '') +
            A.pill(r.st) + A.howHTML('succession') + '</div></div>';
        }).join('');
    };

    var predsHTML = function (list) {
      return list.map(function (p) {
        if (p.deja) {
          return '<div class="jl-pr__acc jl-pr__acc--lvl2 is-dead"><div class="jl-pr__h jl-pr__h--inerte">' +
            '<span style="width:12px;display:inline-block"></span><span class="jl-pr__ttl">' +
            '<a href="' + p.lf + '" title="Ouvrir sur Légifrance">' + esc(p.titre) + '</a> ' +
            '<span class="jl-nor">' + esc(p.nor || '') + '</span></span>' +
            '<span class="jl-pr__cnt">déjà listé plus haut (pris pour lui)</span></div></div>';
        }
        return '<div class="jl-pr__acc jl-pr__acc--lvl2' + clsOf(p.st) + '" data-acc>' +
          '<button type="button" class="jl-pr__h">' + CHEV + '<span class="jl-pr__ttl">' +
          esc(p.titre) + ' <span class="jl-nor">' + esc(p.nor || '') + '</span></span>' +
          '<span class="jl-pr__cnt">' +
          (p.st.k === 'ab' ? '<span class="jl-pr__ab">' + esc(p.st.label) + '</span>' : A.pill(p.st)) +
          (p.retouches.length ? ' · ' + A.acc(p.retouches.length, 'retouche') : '') +
          (p.predecesseurs.length ? ' · a remplacé ' + p.predecesseurs.length : '') + '</span></button>' +
          '<div class="jl-pr__body"><div class="jl-lt__long">' + esc(p.long) + '</div>' +
          '<div class="jl-lt__meta">' + (p.nor ? '<span class="jl-nor">' + esc(p.nor) + '</span>' : '') +
          '<span>en vigueur du ' + fmtCourt(p.debut) + ' au ' + fmtCourt(p.fin) + '</span>' +
          A.pill(p.st) + A.howHTML('succession') +
          '<a href="' + p.lf + '" rel="external noopener">Légifrance ↗</a></div>' +
          retsHTML(p) +
          (p.predecesseurs.length ? '<div class="jl-h2" data-espace="haut">A remplacé ' +
            '<span class="jl-hcount">' + p.predecesseurs.length + '</span></div>' +
            predsHTML(p.predecesseurs) : '') +
          '</div></div>';
      }).join('');
    };

    var arr = function (a) {
      var friseA = '<div class="jl-pr__frise"><span class="jl-pr__seg">' +
        '<i class="jl-point' + (a.st.k !== 'ok' ? ' jl-point--morte' : '') + '"></i>pris le ' +
        fmtCourt(a.debut) + '</span>' +
        a.retouches.map(function (r) {
          return '<span class="jl-pr__lnk"></span><span class="jl-pr__seg' + futCls(r.date_texte) +
            '" data-r="' + r.id + '"><i class="jl-point"></i>retouché ' + fmtCourt(r.date_texte) + '</span>';
        }).join('') +
        (a.fin < '2999'
          ? '<span class="jl-pr__lnk"></span><span class="jl-pr__seg' + (a.fin <= H.at ? '' : ' jl-hfutur') +
            '"><i class="jl-point jl-point--morte"></i>' + (a.fin <= H.at ? 'abrogé' : 'sera abrogé') + ' ' +
            fmtCourt(a.fin) + (a.abrogePar ? ' par ' + esc(A.minus(a.abrogePar.titre)) : '') + '</span>'
          : '<span class="jl-pr__lnk"></span><span class="jl-pr__seg"><i class="jl-point"></i>toujours en vigueur</span>') +
        '</div>';
      var preds = a.predecesseurs.length
        ? '<div class="jl-h2" data-espace="haut">A remplacé <span class="jl-hcount">' +
          a.predecesseurs.length + '</span></div>' + predsHTML(a.predecesseurs)
        : '<div class="jl-pr__foot">Aucun arrêté antérieur remplacé.</div>';
      /* Renvoi RETOUR : si cet arrêté figure aussi comme retouche d'un autre,
         on le dit ici (G2-5 : le renvoi n'était qu'à sens unique). */
      var aussiRet = [];
      H.arretes.forEach(function (b) {
        b.retouches.forEach(function (r) { if (r.id === a.id) aussiRet.push(b); });
      });
      return '<div class="jl-pr__acc jl-pr__acc--lvl1 is-open' + clsOf(a.st) + '" data-acc>' +
        '<button type="button" class="jl-pr__h">' + CHEV + '<span class="jl-pr__ttl">' + esc(a.titre) +
        '</span><span class="jl-pr__cnt">' + A.acc(a.retouches.length, 'retouche') + ' · ' +
        (a.predecesseurs.length ? 'a remplacé ' + a.predecesseurs.length : 'n’a rien remplacé') +
        ' ' + A.pill(a.st) + '</span></button>' +
        '<div class="jl-pr__body"><div class="jl-lt__long">' + esc(a.long) + '</div>' +
        '<div class="jl-lt__meta">' + (a.nor ? '<span class="jl-nor">' + esc(a.nor) + '</span>' : '') +
        (a.date_texte ? '<span>signé le ' + fmtCourt(a.date_texte) + '</span>' : '') +
        '<span>' + A.acc(a.nb_articles, 'article') + '</span>' + A.pill(a.st) + A.howHTML('visa') +
        '<a href="' + a.lf + '" rel="external noopener">Légifrance ↗</a></div>' +
        (aussiRet.length ? '<div class="jl-pr__foot">Il retouche aussi ' +
          aussiRet.map(function (b) { return esc(A.minus(b.titre)); }).join(', ') +
          ' : il figure alors plus bas comme « arrêté modificateur ».</div>' : '') +
        friseA + retsHTML(a) + '<div class="jl-pr__in">' + preds + '</div></div></div>';
    };

    return '<div class="jl-hbar"><span class="jl-surtitre">Poupées russes</span>' +
      '<span class="jl-muted jl-sub jl-sub--enligne">L’article contient ses rédactions ; chaque ' +
      'arrêté pris pour lui contient ses retouches et les arrêtés qu’il a lui-même remplacés, ' +
      'chacun avec les siens (2025 › 20 mai 2020 › 2009-2011). L’article et ses arrêtés sont ' +
      'ouverts ; les arrêtés remplacés se déplient à la demande.</span>' +
      '<button type="button" class="jl-filtre" id="pr-all">tout déplier</button>' +
      '<span class="jl-hcount">' + A.acc(H.counts.total, 'événement') + '</span></div>' +
      '<div class="jl-pr">' +
        '<div class="jl-pr__acc jl-pr__acc--lvl0 is-open" data-acc>' +
        '<button type="button" class="jl-pr__h">' + CHEV + '<span class="jl-pr__ttl">art. ' +
        esc(H.num) + ' · ' + esc(H.cname) + '</span><span class="jl-pr__cnt">niveau 0 · ' +
        A.acc(H.redactions.length, 'rédaction') + '</span></button>' +
        '<div class="jl-pr__body">' + friseArt + '<div class="jl-pr__in">' + redBlocks + '</div></div></div>' +
        '<div class="jl-h2" data-espace="haut">Ce qui a été pris pour lui <span class="jl-hcount">' +
        A.acc(H.arretes.length, 'arrêté') + ', vivants et morts</span></div>' +
        H.arretes.slice().reverse().map(arr).join('') +
      '</div>';
  }

  function wirePoupees() {
    $$('[data-acc] > .jl-pr__h').forEach(function (h) {
      h.addEventListener('click', function (e) {
        e.stopPropagation();
        h.parentElement.classList.toggle('is-open');
      });
    });
    var all = $('#pr-all');
    all.addEventListener('click', function () {
      var on = all.classList.toggle('is-on');
      $$('[data-acc]').forEach(function (a) { a.classList.toggle('is-open', on); });
      all.textContent = on ? 'tout replier' : 'tout déplier';
    });
    /* Surlignage croisé frise ↔ liste des retouches. */
    var surligne = function (id, on) {
      $$('[data-r="' + (global.CSS && CSS.escape ? CSS.escape(id) : id) + '"]').forEach(function (x) {
        x.classList.toggle('is-hl', on);
      });
    };
    document.addEventListener('mouseover', function (e) {
      var t = e.target.closest && e.target.closest('[data-r]');
      if (t) surligne(t.dataset.r, true);
    });
    document.addEventListener('mouseout', function (e) {
      var t = e.target.closest && e.target.closest('[data-r]');
      if (t) surligne(t.dataset.r, false);
    });
  }

  /* ═══════════════ Chrome commun et bascule ════════════════════════════ */

  function chrome(vue) {
    var cur = H.cur;
    var q = new URLSearchParams(location.search);
    var dq = q.get('date') ? '?date=' + encodeURIComponent(q.get('date')) : '';
    return '<div class="jl-fil jl-fil--barre"><a href="article.html' + dq + '">← Retour à l’état actuel</a>' +
      '<span class="jl-vue" title="Changer de vue" role="tablist">' +
      '<button type="button" role="tab" data-vue="couloirs"' + (vue === 'couloirs' ? ' class="is-on" aria-selected="true"' : ' aria-selected="false"') + '>Couloirs</button>' +
      '<button type="button" role="tab" data-vue="poupees"' + (vue === 'poupees' ? ' class="is-on" aria-selected="true"' : ' aria-selected="false"') + '>Poupées russes</button>' +
      '</span></div>' +

      /* <div> et non <p> : le popover de date contient un <div>, qu'un <p>
         fermerait d'office (le bouton n'aurait alors plus rien à ouvrir). */
      '<div class="jl-leadrow"><div class="jl-lead"><b>' +
      (vue === 'couloirs' ? 'Couloirs' : 'Poupées russes') + '.</b> ' +
      (vue === 'couloirs'
        ? 'Une ligne par texte et le temps en abscisse : on voit d’un coup d’œil qui vivait en même temps que qui, et quelle barre a pris la place de quelle autre.'
        : 'Des accordéons emboîtés : l’article contient ses rédactions, chaque arrêté pris pour lui contient ses retouches et les arrêtés qu’il a lui-même remplacés, chacun avec les siens.') +
      ' ' + A.whenBadge(H, 'l’historique') + ' ' +
      A.datePopHTML(H, H.redactions.map(function (R) { return R.debut; })) + '</div></div>' +

      A.bandeHTML([
        { k: 'État à la date lue', v: cur
            ? A.pill(A.lifeAt(cur, H.at)) + ' depuis le ' + fmtCourt(cur.date_debut)
            : A.pill({ k: 'fut', label: 'n’existe pas encore', why: 'la date lue précède la première rédaction' }) },
        { k: 'Rédactions', v: H.counts.redactions + ' depuis ' + fmtCourt(H.redactions[0].debut) },
        { k: 'Événements retenus ' + A.aide('Un événement, c’est une date où quelque chose arrive à ' +
            'l’article ou à un texte pris pour lui : une rédaction écrite, un arrêté pris, retouché, ' +
            'abrogé ou remplacé. Le décompte suit la règle de périmètre rappelée en bas de page.'),
          v: '<b class="jl-mono">' + H.counts.total + '</b> <span class="jl-muted">· ' +
            A.acc(H.counts.n0, 'rédaction') + ' · ' +
            A.acc(H.counts.n1, 'événement d’arrêté', 'événements d’arrêtés') + ' · ' +
            H.counts.n2 + ' retouches et prédécesseurs' +
            (H.isToday ? '' : ' · <b>' + H.counts.avant + ' avant la date lue</b>, ' +
              H.counts.apres + ' après') + '</span>' },
        { k: 'Textes en jeu ' + A.aide('Tous les textes affichés sur cette page, comptés une seule ' +
            'fois : l’article, les arrêtés pris pour lui, leurs retouches et leurs prédécesseurs. ' +
            '« En vigueur » s’entend à la date lue.'),
          v: A.acc(H.counts.textes, 'texte') +
            (H.counts.distincts < H.counts.textes
              ? ' <span class="jl-muted" title="Légifrance a ouvert un second identifiant pour un même arrêté (même NOR) lors d’un renommage : il apparaît sous ses deux entrées.">(' +
                H.counts.distincts + ' distincts)</span>' : '') +
            ', ' + H.counts.vivants + ' en vigueur à la date lue' },
        { k: 'Objet', v: H.recycled ? '<span class="jl-warnp">numéro recyclé</span>'
                                    : 'inchangé depuis l’origine' }
      ]);
  }

  function honnetete() {
    return '<div class="jl-honnetete jl-hhonest"><b>Ce que cette page montre, et ce qu’elle laisse ' +
      'dehors.</b> L’historique retient la vie de l’article (ses ' + H.counts.redactions +
      ' rédactions et le texte qui a écrit chacune) et la vie de ce qui est pris pour lui : les ' +
      H.counts.arretes + ' arrêtés qui le visent, vivants ou morts, leurs retouches et leurs ' +
      'prédécesseurs abrogés, de proche en proche. <b>' +
      A.acc(H.counts.exclus, 'texte écarté', 'textes écartés') + '</b> : ' +
      H.exclus.map(function (x) {
        return '<a href="' + x.lf + '">' + esc(x.titre) + '</a>' +
          (x.nor ? ' <span class="jl-nor">' + esc(x.nor) + '</span>' : '') +
          (x.raison ? ' <span class="jl-muted">(' + esc(x.raison) + ')</span>' : '');
      }).join(' · ') + '. ' +
      'Ces textes ne sont là que parce qu’un texte retenu les modifie au passage ; ils ne relèvent ' +
      'pas de l’article. Un décret peut retoucher un arrêté (le décret 2019-966 a remplacé ' +
      '« tribunal de grande instance » par « tribunal judiciaire » dans des centaines de textes) : ' +
      'il apparaît alors comme « décret modificateur ». ' +
      (H.isToday ? '' : '<br>Lecture au ' + fmtCourt(H.at) + ' : ce qui n’existe pas encore à cette ' +
        'date est en bleu (« entre en vigueur le … ») et atténué ; les compteurs distinguent avant ' +
        'et après.') + '</div>';
  }

  function vueDemandee() {
    var v = new URLSearchParams(location.search).get('vue');
    return v === 'poupees' ? 'poupees' : 'couloirs';
  }

  function dessine(vue) {
    document.title = 'Historique de l’article ' + H.num + ' · ' + H.cname + ' · JusticeLibre';
    $('#jl-titre').innerHTML = 'Article <em>' + esc(H.num) + '</em> · ' + esc(H.cname) +
      ' <span class="jl-kicker--pilule">historique</span>';
    $('#jl-corps').innerHTML = chrome(vue) +
      (vue === 'couloirs' ? vueCouloirs() : vuePoupees()) + honnetete();

    if (vue === 'couloirs') wireCouloirs(); else wirePoupees();

    J.bindDatePop(function (d) {
      var q = new URLSearchParams(location.search);
      q.set('date', d); q.set('num', H.num); q.set('vue', vue);
      location.search = q.toString();
    });
    /* La bascule ne recharge pas la page et CONSERVE la date lue. */
    $$('[data-vue]').forEach(function (b) {
      b.addEventListener('click', function () {
        var v = b.dataset.vue;
        if (v === vue) return;
        var q = new URLSearchParams(location.search);
        q.set('vue', v);
        history.replaceState(null, '', location.pathname + '?' + q.toString());
        dessine(v);
        window.scrollTo(0, 0);
      });
    });
  }

  A.loadHisto().then(function (h) {
    H = h; global.H = h;
    dessine(vueDemandee());
  }).catch(function (e) {
    $('#jl-corps').innerHTML = '<div class="jl-alerte jl-alerte--icone">⚠ <div><b>Chargement ' +
      'impossible.</b> ' + esc(e.message) + '</div></div>';
    console.error(e);
  });
})(window);
