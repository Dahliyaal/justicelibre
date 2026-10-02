/* Chiffres du corpus, recomptés chaque nuit dans les bases (scripts/compte_corpus.py
   → /corpus.json). Tout élément [data-k="<fonds>"] reçoit le chiffre du fonds ;
   [data-k-date] reçoit la date du comptage. En cas d'échec, le chiffre écrit en
   dur dans la page reste affiché : jamais de case vide ni de faux zéro. */
(function(){
  function fmt(n, style){
    if(style === 'brut') return String(n);
    if(n >= 1e6) return (Math.round(n/1e5)/10).toString().replace('.', ',') + ' M';
    return n.toLocaleString('fr-FR');
  }
  fetch('/corpus.json', {cache: 'no-store'}).then(function(r){ return r.ok ? r.json() : null; }).then(function(d){
    if(!d || !d.fonds) return;
    document.querySelectorAll('[data-k]').forEach(function(el){
      var n = d.fonds[el.getAttribute('data-k')];
      if(typeof n === 'number' && n > 0) el.textContent = fmt(n, el.getAttribute('data-k-fmt'));
    });
    if(d.compte_le){
      var dt = new Date(d.compte_le);
      if(!isNaN(dt)) document.querySelectorAll('[data-k-date]').forEach(function(el){
        el.textContent = ' (dernier comptage : ' + dt.toLocaleDateString('fr-FR', {day:'numeric', month:'long', year:'numeric'}) + ')';
      });
    }
  }).catch(function(){});
})();
