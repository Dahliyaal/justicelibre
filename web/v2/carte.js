/**
 * carte.js — rendu de web/v2/article.html (la page « MAINTENANT »).
 *
 * Porté de web/maquettes/carte-748.html (variante 2 « Arbre », validée).
 * Modèle : ART.loadModel() dans article.js. Composants : jl.css §28.
 *
 * Règle de fond : la page est au présent. L'archéologie est derrière le bouton
 * « Historique » et derrière le changement de date, jamais dans le corps.
 */
(function (global) {
  'use strict';
  var J = global.JL, A = global.ART;
  var HORLOGE = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>';
  var esc = J.esc, fmtDate = J.fmtDate, fmtCourt = J.fmtCourt, $ = J.$;

  /* ═══════════════ Briques ═════════════════════════════════════════════ */

  function metaHTML(x) {
    return '<div class="jl-lt__meta">' +
      (x.date ? '<span>' + fmtCourt(x.date) + '</span>' : '') +
      (x.nor ? '<span class="jl-nor">' + esc(x.nor) + '</span>' : '') +
      A.pill(x.st) + A.howHTML(x.how) + '</div>';
  }
  function lienTitre(x) { return '<a href="' + x.lf + '">' + esc(x.titre) + '</a>'; }

  /* « remplace l'arrêté du … » — avec le `minus` tranché (article défini inclus),
     donc SANS article défini en dur devant, sinon on écrirait « l'l'arrêté ». */
  function remplaceHTML(a) {
    if (!a.remplace.length) return '';
    if (a.remplace.length === 1) {
      return '<div class="jl-lt__more">remplace <a href="historique.html' + dq() +
        '" title="voir l’historique">' + esc(A.minus(a.remplace[0].titre)) + '</a></div>';
    }
    return '<div class="jl-lt__more">remplace <a href="historique.html' + dq() + '" title="' +
      esc(a.remplace.map(function (r) { return r.titre; }).join(' · ')) + '">' +
      a.remplace.length + ' arrêtés antérieurs</a></div>';
  }

  var M = null;
  function dq() { return M && !M.isToday ? '?date=' + encodeURIComponent(M.at) : ''; }

  /* ═══════════════ Colonne de gauche : le cadre normatif ═══════════════ */

  /* Article de valeur réglementaire : pas d'étage « décrets d'application ».
     Les décrets qui le mentionnent sont à droite (références croisées). */
  var ETAGES = [
    { titre: 'La rédaction en vigueur', vide: 'aucun texte modificateur relié dans LEGI' },
    { titre: 'Arrêtés en vigueur pris pour lui', vide: 'aucun arrêté en vigueur n’est pris pour lui' }
  ];

  function gauche(M) {
    var D = [M.etage1, M.etage3];
    var item = function (x, extra) {
      return '<div class="jl-lt">' +
        '<div class="jl-lt__rel">' + esc(x.rel) + '</div>' +
        '<div class="jl-lt__t">' + lienTitre(x) + '</div>' +
        (x.long ? '<div class="jl-lt__long">' + esc(x.long) + '</div>' : '') +
        metaHTML(x) +
        (x.depuis ? '<div class="jl-lt__more">en vigueur depuis le ' + fmtCourt(x.depuis) + ' · ' +
          A.acc(M.versions.indexOf(M.cur), 'réécriture') + ' avant celle-ci · ' +
          '<a href="historique.html' + dq() + '">historique</a></div>' : '') +
        (extra || '') + '</div>';
    };
    var node = function (h, last) { return '<div class="jl-noeud' + (last ? ' jl-noeud--last' : '') + '">' + h + '</div>'; };
    var arr = function (a, last) {
      var kids = a.retouches.length
        ? '<div class="jl-kids">' + a.retouches.map(function (r, j) {
            return node(item(r), j === a.retouches.length - 1);
          }).join('') + '</div>'
        : '';
      return node(item(a, remplaceHTML(a)) + kids, last);
    };
    var branche = function (e, i) {
      var rows = D[i];
      var body = rows.length
        ? (i === 1 ? rows.map(function (a, j) { return arr(a, j === rows.length - 1); }).join('')
                   : rows.map(function (x, j) { return node(item(x), j === rows.length - 1); }).join(''))
        : node('<div class="jl-empty">' + esc(e.vide) + '</div>', true);
      return '<div class="jl-etage"><div class="jl-etage__t">' + esc(e.titre) +
        '<span class="jl-etage__c">' + rows.length + '</span></div>' + body + '</div>';
    };
    return '<div class="jl-coltete"><h2>Cadre normatif actuel</h2>' + A.whenBadge(M) + '</div>' +
      '<p class="jl-sub">Présentation hiérarchique, du texte qui a écrit la rédaction en vigueur ' +
      'aux arrêtés pris pour l’appliquer. Article de valeur réglementaire : aucun décret ' +
      'd’application ne lui est supérieur.</p>' +
      '<div class="jl-arbre"><div class="jl-racine">art. ' + esc(M.num) + ' CPC</div>' +
      ETAGES.map(branche).join('') + '</div>' +
      '<div class="jl-colfoot"><a href="historique.html' + dq() + '">↺ Historique</a></div>';
  }

  /* ═══════════════ Colonne du milieu : le texte à la date lue ══════════ */

  var alineas = function (v) { return (v.texte || '').split(/(?<=\.)\s+(?=[A-Z])/); };

  function milieu(M) {
    var cur = M.cur;
    if (!cur) return '<div class="jl-honnetete">À la date lue, l’article n’existe pas encore.</div>';
    return alineas(cur).map(function (a, i) {
      return '<p class="jl-alin"><span class="jl-al">al. ' + (i + 1) + '</span>' +
        A.linkArts(A.linkArtsLEGI(esc(a), cur.liens), 'CPC') + '</p>';
    }).join('') +
      (cur.nota ? '<div class="jl-nota"><b>Nota.</b> ' + esc(cur.nota) + '</div>' : '');
  }

  /* ═══════════════ Colonne de droite : références croisées ═════════════ */

  function droite(M) {
    return M.citantsList.map(function (c) {
      return '<div class="jl-lt jl-lt--separee' + (c.st.k !== 'ok' ? ' jl-lt--morte' : '') + '">' +
        '<div class="jl-lt__rel">' + esc(A.NATLABEL[c.nature] || String(c.nature).toLowerCase()) +
        Array.from(c.how).map(function (h) { return A.howHTML(h); }).join('') + '</div>' +
        '<div class="jl-lt__t"><a href="' + c.lf + '">' + esc(c.titre) + '</a>' +
        (c.arts.length ? ' <span class="jl-muted">· art. ' + esc(c.arts.join(', ')) + '</span>' : '') + '</div>' +
        '<div class="jl-lt__meta">' + (c.date ? '<span>' + fmtCourt(c.date) + '</span>' : '') +
        (c.nor ? '<span class="jl-nor">' + esc(c.nor) + '</span>' : '') + A.pill(c.st) + '</div></div>';
    }).join('') || '<div class="jl-empty">aucun texte ne le cite</div>';
  }

  /* ═══════════════ Jurisprudence qui le cite ═══════════════════════════ */

  /* La phrase d'honnêteté est reproduite AU MOT PRÈS : c'est un engagement
     éditorial, pas une formulation. */
  var HONNETETE_JURIS = '<b>Ne sont listées que les décisions qui citent exactement cette ' +
    'référence</b> (« article 748-6 » avec « code de procédure civile » ou « CPC » sur la même ' +
    'page). Les renvois indirects (« du même code », « l’article précité ») ne sont pas encore ' +
    'captés : ce travail est en cours.';

  function jurisHTML(M) {
    if (!M.C) {
      return '<section class="jl-juris" id="jurisprudence"><h2 class="jl-titre jl-titre--nu">' +
        'Jurisprudence qui le cite <span class="jl-n">indisponible</span></h2>' +
        '<div class="jl-honnetete">Le fichier de décisions n’a pas pu être chargé.</div></section>';
    }
    var per = Object.keys(M.C.per_source || {}).filter(function (k) { return M.C.per_source[k]; })
      .map(function (k) { return esc(A.SRC[k] || k) + ' ' + J.nb(M.C.per_source[k]); }).join(' · ');
    return '<section class="jl-juris" id="jurisprudence"><h2 class="jl-titre jl-titre--nu">' +
      'Jurisprudence qui le cite <span class="jl-n">' + J.plur(M.juri.length, 'décision') + ' · ' +
      J.nb(M.C.total_lexical) + ' pages lexicales brutes' +
      (M.fusion ? ' · ' + J.plur(M.fusion, 'doublon') + ' fusionné' + (M.fusion > 1 ? 's' : '') : '') +
      '</span></h2>' +
      '<div class="jl-honnetete">' + HONNETETE_JURIS + ' Requête : <span class="jl-mono">' +
      esc(M.C.requete) + '</span> · ' + per + '. ' + esc(M.C.avertissement || '') + '</div>' +
      '<div class="jl-jgrid">' + M.juri.map(function (x) {
        return '<article class="jl-jc' + (x.differs && x.v ? ' jl-jc--ancienne' : '') +
          ' jl-jc--' + x.fam + '">' +
          '<div class="jl-jc__m"><span class="jl-tag jl-tag--' + x.fam + '">' + A.FAMLABEL[x.fam] + '</span>' +
          '<span class="jl-src">' + esc(A.SRC[x.source] || x.source) + '</span>' +
          '<span class="jl-mono">' + fmtCourt(x.date) + '</span>' +
          (x.ids.length > 1 ? A.howHTML(x.ids.length + ' clés') : '') + '</div>' +
          '<div class="jl-jc__t"><a href="' + x.href + '">' + esc(x.juridiction) + (x.numero ? ', n° ' + esc(x.numero) : ', <span class="jl-muted jl-poids-normal">pourvoi non renseigné</span>') + '</a></div>' +
          '<div class="jl-jc__x">« ' + esc(x.extract) + ' »</div>' +
          '<div class="jl-jc__ap">' +
          (x.publication ? '<span class="jl-src">' + esc(x.publication) + '</span>' : '') +
          // Sous quelle rédaction le juge a-t-il lu l'article ? Une phrase, pas deux
          // badges (« rédaction 2019 » + « rédaction différente de celle lue » était
          // illisible, 13 sept. 2026). Le lien bascule la page à cette date.
          // Variante retenue par la propriétaire (13 sept.) : ligne de pied sous un filet,
          // petite horloge, phrase courte, lien vers la rédaction que la cour a lue.
          '</div><div class="jl-jc__foot' + (x.differs && x.v ? ' jl-jc__foot--ancienne' : '') + '">' + HORLOGE +
          (x.v ? (x.v === M.cur
              ? '<span title="La rédaction en vigueur au jour de la décision est celle affichée.">Jugé sous la rédaction affichée.</span>'
              : '<span title="La rédaction réellement applicable dépend aussi des dispositions transitoires du texte modificateur (voir le Nota), pas seulement de la date.">' +
                'Jugé sous la rédaction de ' + x.v.date_debut.slice(0, 4) + '.</span>' +
                '<a class="jl-jc__lire" href="?date=' + esc(x.v.date_debut) + '&num=' + esc(M.num) + '#jurisprudence">Lire la rédaction de ' + x.v.date_debut.slice(0, 4) + '</a>')
               : '<span title="La date de la décision ne tombe dans aucune rédaction connue.">Hors rédaction connue.</span>') +
          '</div></article>';
      }).join('') + '</div></section>';
  }

  /* ═══════════════ Copier pour un LLM ══════════════════════════════════ */

  /* Rédaction datée, liens LEGI, cadre normatif, provenance. Le texte est lu
     dans le MODÈLE, pas dans le DOM : ce qui est copié ne peut pas diverger de
     ce qui est affiché parce que les deux sortent de la même source. */
  function texteLLM(M) {
    var cur = M.cur;
    var lignes = [];
    lignes.push('ARTICLE DE LOI (source officielle Légifrance, données LEGI)');
    lignes.push('Référence : article ' + M.num + ' du ' + M.cname.toLowerCase());
    lignes.push('Rédaction lue : ' + (cur
      ? 'celle en vigueur au ' + fmtDate(M.at) + ', applicable du ' + fmtDate(cur.date_debut) +
        (cur.date_fin && cur.date_fin < '2999' ? ' au ' + fmtDate(cur.date_fin) : ' (toujours en vigueur)')
      : 'aucune — l’article n’existe pas à cette date'));
    if (cur) {
      lignes.push('Identifiant LEGI : ' + cur.legiarti);
      lignes.push('Source : https://www.legifrance.gouv.fr/codes/article_lc/' + cur.legiarti);
      lignes.push('');
      lignes.push('TEXTE :');
      alineas(cur).forEach(function (a, i) { lignes.push('al. ' + (i + 1) + '. ' + a); });
      if (cur.nota) lignes.push('Nota. ' + cur.nota);
    }
    lignes.push('');
    lignes.push('CADRE NORMATIF À CETTE DATE :');
    if (!M.etage1.length && !M.etage3.length) lignes.push('(aucun texte relié)');
    M.etage1.forEach(function (x) {
      lignes.push('- ' + x.rel + ' : ' + x.titre + (x.nor ? ' [NOR ' + x.nor + ']' : '') +
        ' — ' + x.st.label + ' — ' + x.lf);
    });
    M.etage3.forEach(function (a) {
      lignes.push('- pris pour lui : ' + a.titre + (a.nor ? ' [NOR ' + a.nor + ']' : '') +
        ' — ' + a.st.label + ' — ' + a.lf);
      a.retouches.forEach(function (r) {
        lignes.push('    · retouché par : ' + r.titre + (r.nor ? ' [NOR ' + r.nor + ']' : '') + ' — ' + r.lf);
      });
      if (a.remplace.length) {
        lignes.push('    · remplace ' + a.remplace.length + ' arrêté(s) antérieur(s) : ' +
          a.remplace.map(function (r) { return r.titre; }).join(' ; '));
      }
    });
    if (M.citantsList.length) {
      lignes.push('');
      lignes.push('TEXTES DE MÊME RANG OU SUPÉRIEUR QUI LE MENTIONNENT :');
      M.citantsList.forEach(function (c) {
        lignes.push('- ' + (A.NATLABEL[c.nature] || c.nature) + ' : ' + c.titre +
          (c.arts.length ? ' (art. ' + c.arts.join(', ') + ')' : '') + ' — ' + c.st.label + ' — ' + c.lf);
      });
    }
    lignes.push('');
    lignes.push('PROVENANCE : base LEGI (Légifrance), Licence Ouverte 2.0. « lien LEGI » = lien ' +
      'posé par Légifrance ; « visa » = le texte cite l’article dans ses visas ; « succession » = ' +
      'lien « modifie » ou « abroge » entre deux textes dans LEGI. JusticeLibre est une copie ' +
      'miroir indexée ; la version qui fait foi est celle de Légifrance.');
    lignes.push('Consignes pour l’assistant : citer la rédaction par sa date d’entrée en vigueur ; ' +
      'ne rien attribuer à cet article qui ne figure pas dans le texte ci-dessus ; la rédaction ' +
      'réellement applicable à un litige dépend aussi des dispositions transitoires.');
    return lignes.join('\n') + '\n';
  }

  function bindLLM(M) {
    var btn = $('[data-art-llm]');
    if (!btn) return;
    var lab = btn.querySelector('[data-art-llm-label]') || btn;
    btn.addEventListener('click', function () {
      var out = texteLLM(M), repos = lab.textContent;
      J.copy(out).then(function () {
        lab.textContent = 'Copié (' + Math.round(out.length / 1000) + ' k car.)';
        setTimeout(function () { lab.textContent = repos; }, 2500);
      }, function () {
        lab.textContent = 'Échec de la copie';
        setTimeout(function () { lab.textContent = repos; }, 2500);
      });
    });
  }

  /* ═══════════════ Page ════════════════════════════════════════════════ */

  function render(m) {
    M = m;
    var at = M.at, cur = M.cur;
    document.title = 'Article ' + M.num + ' · ' + M.cname + ' · JusticeLibre';

    $('#jl-titre').innerHTML = 'Article <em>' + esc(M.num) + '</em> · ' + esc(M.cname);

    $('#jl-corps').innerHTML =
      /* <div> et non <p> : le popover contient un <div>, qu'un <p> fermerait
         d'office (le parseur le sortirait du .jl-datew, et le bouton n'aurait
         plus rien à ouvrir). */
      '<div class="jl-leadrow"><div class="jl-lead">En date du <b class="jl-mono">' + fmtDate(at) + '</b> ' +
        A.datePopHTML(M, M.versions.map(function (v) { return v.date_debut; })) + '</div>' +
      '<a class="jl-bouton jl-bouton--cta" href="historique.html' + dq() +
        '" title="Toutes les rédactions, diff mot à mot, histoire de l’article">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" ' +
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/>' +
        '<path d="M12 7v5l3 2"/></svg>Historique</a></div>' +

      A.bandeHTML([
        { k: 'État à la date lue', v: cur
            ? A.pill(A.lifeAt(cur, at)) + ' depuis le ' + fmtCourt(cur.date_debut)
            : A.pill({ k: 'fut', label: 'n’existe pas encore', why: 'la date lue précède la première rédaction' }) },
        { k: 'Rédactions', v: M.versions.length + ' depuis ' + fmtCourt(M.versions[0].date_debut) },
        { k: 'Objet ' + A.aide('Un numéro d’article peut être réutilisé pour une règle qui n’a plus rien à ' +
            'voir avec la précédente, sans passer par une abrogation : Légifrance affiche alors « en ' +
            'vigueur » comme si de rien n’était. On compare ici le vocabulaire de chaque rédaction avec ' +
            'la précédente ; en dessous de 25 % de mots communs, on signale un recyclage.'),
          v: M.recycled ? '<span class="jl-warnp">numéro recyclé</span> la règle a changé de sujet'
                        : 'inchangé depuis l’origine' },
        { k: 'Identifiant', v: '<span class="jl-mono">' + esc(cur ? cur.legiarti : M.versions[0].legiarti) + '</span>' },
        { k: 'Source', v: '<a href="https://www.legifrance.gouv.fr/codes/article_lc/' +
            esc(cur ? cur.legiarti : M.versions[0].legiarti) + '" rel="external noopener">Légifrance ↗</a> ' +
            '<span class="jl-src">LEGI</span>' }
      ]) +

      '<div class="jl-cols">' +
        '<div class="jl-col">' + gauche(M) + '</div>' +
        '<div class="jl-col jl-col--mid"><div class="jl-coltete"><h2>' +
          (M.isToday ? 'Texte en vigueur' : 'Texte au ' + fmtCourt(at)) + '</h2>' +
          '<span class="jl-muted jl-sub jl-sub--enligne" data-align="fin">' +
          (cur ? 'rédaction du ' + fmtCourt(cur.date_debut) +
            (cur.date_fin && cur.date_fin < '2999' ? ' au ' + fmtCourt(cur.date_fin) : '') : '') +
          '</span></div>' + milieu(M) + '</div>' +
        '<div class="jl-col"><div class="jl-coltete"><h2>Références croisées</h2>' +
          '<span class="jl-muted" data-align="fin">' + M.citantsList.length + '</span></div>' +
          '<p class="jl-sub">Textes de même rang ou supérieur qui le mentionnent sans agir sur lui. ' +
          'Les textes qui l’ont écrit et ceux pris pour l’appliquer figurent dans le cadre normatif ' +
          'ou dans l’historique.</p>' + droite(M) + '</div>' +
      '</div>' +

      jurisHTML(M) +

      '<div class="jl-honnetete" data-espace="haut" id="historique"><b>Historique.</b> ' +
      'Toutes ses rédactions, les textes qui les ont écrites, et les textes morts qui ne figurent ' +
      'plus dans le cadre normatif : <a href="historique.html' + dq() + '">vue Couloirs</a> · ' +
      '<a href="historique.html' + dq() + (dq() ? '&' : '?') + 'vue=poupees">vue Poupées russes</a>.</div>';

    J.bindDatePop(function (d) {
      var q = new URLSearchParams(location.search);
      q.set('date', d); q.set('num', M.num);
      location.search = q.toString();
    });
    bindLLM(M);
  }

  A.loadModel().then(function (m) { global.M = m; render(m); }).catch(function (e) {
    $('#jl-corps').innerHTML = '<div class="jl-alerte jl-alerte--icone">⚠ <div><b>Chargement ' +
      'impossible.</b> ' + esc(e.message) + '</div></div>';
    console.error(e);
  });
})(window);
