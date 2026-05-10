/**
 * Composant topbar réutilisable JusticeLibre.
 *
 * Source unique du header — utilisé par :
 *   - search.html (via inclusion <script defer src="/topbar.js"></script>)
 *   - ressources.html (idem)
 *   - index.html (idem)
 *   - SSR pages décisions/lois (via ssr.py:get_topbar_html() qui lit ce JS et
 *     extrait le HTML inline pour le SEO Google/LLM)
 *
 * Détecte automatiquement la page courante et applique class="active" sur le
 * bon lien.
 */

(function(){
  // ─── HTML du header ───────────────────────────────────────────────────
  const TOPBAR_HTML = `
<header class="topbar">
  <a href="/" class="logo-area">
    <img src="/logo.svg" alt="">
    <span class="name">justicelibre<span class="tld">.org</span></span>
    <span class="proto-badge" title="Version bêta - moteur en rodage. Envoyer retour via GitHub ou Ko-fi.">bêta</span>
  </a>
  <nav class="main-nav">
    <a href="/" data-route="/">Accueil</a>
    <a href="/search.html" data-route="/search.html">Recherche</a>
    <a href="/ressources.html" data-route="/ressources.html">Ressources</a>
    <a href="/#connect" data-route="#connect">MCP</a>
    <a href="https://github.com/Dahliyaal/justicelibre">GitHub</a>
    <button class="theme-toggle" id="themeToggle" title="Bascule clair / sombre" aria-label="Changer thème">
      <svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
      <svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
    </button>
  </nav>
  <button class="topbar-burger" id="topbarBurger" aria-label="Menu" aria-expanded="false">
    <span></span><span></span><span></span>
  </button>
</header>
<div class="topbar-drawer" id="topbarDrawer" aria-hidden="true">
  <button class="topbar-drawer-close" id="topbarDrawerClose" aria-label="Fermer">×</button>
  <a href="/" data-route="/">Accueil</a>
  <a href="/search.html" data-route="/search.html">Recherche</a>
  <a href="/ressources.html" data-route="/ressources.html">Ressources</a>
  <a href="/#connect" data-route="#connect">MCP</a>
  <a href="https://github.com/Dahliyaal/justicelibre">GitHub</a>
</div>
<div class="topbar-overlay" id="topbarOverlay"></div>`.trim();

  // ─── CSS du header ────────────────────────────────────────────────────
  // Valeurs en pixels absolus (pas rem) pour rester pixel-identique entre les
  // pages dont le `body` font-size diffère (search.html=15px, ressources=16px).
  // Font-family forcée pour ne pas hériter (Inter vs DM Sans selon page).
  const TOPBAR_CSS = `
.topbar{
  position:sticky;top:0;z-index:100;
  background:rgba(255,255,255,.96);backdrop-filter:blur(8px);
  display:flex;align-items:center;justify-content:space-between;
  padding:13px 40px;
  border-bottom:1px solid var(--line);
  font-size:15px;line-height:normal;
  font-family:'DM Sans','Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
}
.topbar *{line-height:normal}
html[data-theme="dark"] .topbar{background:rgba(34,34,34,.96)}
@media(prefers-color-scheme:dark){html:not([data-theme="light"]) .topbar{background:rgba(34,34,34,.96)}}
.topbar .logo-area{display:flex;align-items:center;gap:13px;color:var(--ink);text-decoration:none}
.topbar .logo-area:hover{text-decoration:none}
.topbar .logo-area img,.topbar .logo-area svg{width:44px;height:44px}
.topbar .logo-area .name{
  font-family:'DM Serif Display',Georgia,serif;
  font-size:17px;color:var(--ink);font-weight:400;
}
.topbar .logo-area .name .tld{color:var(--teal)}
.topbar .proto-badge{
  display:inline-block;margin-left:10px;
  font-size:9px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;
  padding:3px 7px;border:1px solid var(--gold);color:var(--gold);
  border-radius:2px;vertical-align:middle;cursor:help;
  font-family:'DM Sans','Inter',sans-serif;line-height:1.2;
}
.topbar nav.main-nav{display:flex;align-items:center;gap:32px}
.topbar nav.main-nav a{
  font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;
  color:var(--ink);padding-bottom:6px;border-bottom:3px solid transparent;
  text-decoration:none;font-family:inherit;
}
.topbar nav.main-nav a.active{color:var(--teal);border-bottom-color:var(--teal)}
.topbar nav.main-nav a:hover{border-bottom-color:var(--teal);text-decoration:none}
.topbar .theme-toggle{
  background:none;border:1px solid var(--line);color:var(--muted);
  width:34px;height:34px;border-radius:50%;cursor:pointer;
  display:flex;align-items:center;justify-content:center;padding:0;
  transition:color .2s,border-color .2s;
}
.topbar .theme-toggle svg{width:16px;height:16px}
.topbar .theme-toggle .sun{display:none}
html[data-theme="dark"] .topbar .theme-toggle .moon{display:none}
html[data-theme="dark"] .topbar .theme-toggle .sun{display:block}
@media(prefers-color-scheme:dark){
  html:not([data-theme="light"]) .topbar .theme-toggle .moon{display:none}
  html:not([data-theme="light"]) .topbar .theme-toggle .sun{display:block}
}
.topbar .theme-toggle:hover{color:var(--teal);border-color:var(--teal)}

/* ── Mobile : burger + drawer latéral ── */
.topbar-burger{
  display:none;background:none;border:none;cursor:pointer;
  width:40px;height:40px;padding:8px;flex-direction:column;
  justify-content:space-between;align-items:stretch;
}
.topbar-burger span{
  display:block;height:2px;background:var(--ink);border-radius:2px;
  transition:transform .25s,opacity .25s;
}
.topbar-burger.open span:nth-child(1){transform:translateY(8px) rotate(45deg)}
.topbar-burger.open span:nth-child(2){opacity:0}
.topbar-burger.open span:nth-child(3){transform:translateY(-8px) rotate(-45deg)}
.topbar-drawer{
  position:fixed;top:0;right:0;bottom:0;width:280px;max-width:85vw;
  background:var(--white);border-left:1px solid var(--line);
  transform:translateX(100%);transition:transform .25s ease-out;
  z-index:200;padding:80px 24px 24px;
  display:flex;flex-direction:column;gap:6px;
  box-shadow:-4px 0 24px rgba(0,0,0,.08);
  font-family:'DM Sans','Inter',sans-serif;
}
html[data-theme="dark"] .topbar-drawer{background:#222}
@media(prefers-color-scheme:dark){html:not([data-theme="light"]) .topbar-drawer{background:#222}}
.topbar-drawer.open{transform:translateX(0)}
.topbar-drawer-close{
  position:absolute;top:18px;right:18px;
  background:none;border:none;cursor:pointer;
  width:38px;height:38px;border-radius:50%;
  font-size:28px;line-height:1;color:var(--ink);
  display:flex;align-items:center;justify-content:center;padding:0 0 4px;
  transition:background .15s;
}
.topbar-drawer-close:hover{background:var(--cream)}
html[data-theme="dark"] .topbar-drawer-close:hover{background:#333}
.topbar-drawer a{
  font-size:14px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;
  color:var(--ink);padding:14px 4px;border-bottom:1px solid var(--line);
  text-decoration:none;
}
.topbar-drawer a:last-child{border-bottom:none}
.topbar-drawer a.active{color:var(--teal)}
.topbar-overlay{
  position:fixed;inset:0;background:rgba(0,0,0,.4);opacity:0;
  pointer-events:none;transition:opacity .25s;z-index:150;
}
.topbar-overlay.open{opacity:1;pointer-events:auto}
@media(max-width:860px){
  .topbar nav.main-nav a{display:none}
  .topbar nav.main-nav .theme-toggle{display:flex}
  .topbar-burger{display:flex}
}`;

  // ─── Injection ────────────────────────────────────────────────────────
  function inject() {
    // CSS dans le <head>
    if (!document.querySelector('style[data-topbar-injected]')) {
      const style = document.createElement('style');
      style.setAttribute('data-topbar-injected', '1');
      style.textContent = TOPBAR_CSS;
      document.head.appendChild(style);
    }
    // HTML : insère au début du <body>, AVANT tout autre contenu.
    // insertAdjacentHTML supporte plusieurs siblings (vs outerHTML qui parfois
    // ne garde que le premier).
    const mount = document.querySelector('[data-topbar-mount]');
    if (mount) {
      mount.insertAdjacentHTML('beforebegin', TOPBAR_HTML);
      mount.remove();
    } else if (!document.querySelector('header.topbar')) {
      document.body.insertAdjacentHTML('afterbegin', TOPBAR_HTML);
    }

    // Active la nav courante (sur la nav du header ET le drawer mobile)
    const path = location.pathname;
    document.querySelectorAll('header.topbar nav.main-nav a[data-route], .topbar-drawer a[data-route]').forEach(a => {
      const route = a.getAttribute('data-route');
      if (route === path || (path === '/' && route === '/') ||
          (path.endsWith('/search.html') && route === '/search.html') ||
          (path.endsWith('/ressources.html') && route === '/ressources.html')) {
        a.classList.add('active');
      }
    });

    // Wire burger mobile : ouvre/ferme le drawer
    const burger = document.getElementById('topbarBurger');
    const drawer = document.getElementById('topbarDrawer');
    const overlay = document.getElementById('topbarOverlay');
    function setDrawer(open) {
      if (!burger || !drawer || !overlay) return;
      burger.classList.toggle('open', open);
      drawer.classList.toggle('open', open);
      overlay.classList.toggle('open', open);
      burger.setAttribute('aria-expanded', open ? 'true' : 'false');
      drawer.setAttribute('aria-hidden', open ? 'false' : 'true');
    }
    if (burger) burger.addEventListener('click', () => {
      const isOpen = drawer && drawer.classList.contains('open');
      setDrawer(!isOpen);
    });
    if (overlay) overlay.addEventListener('click', () => setDrawer(false));
    const closeBtn = document.getElementById('topbarDrawerClose');
    if (closeBtn) closeBtn.addEventListener('click', () => setDrawer(false));
    if (drawer) drawer.querySelectorAll('a').forEach(a => a.addEventListener('click', () => setDrawer(false)));
    document.addEventListener('keydown', e => { if (e.key === 'Escape') setDrawer(false); });

    // Wire theme toggle
    const KEY = 'jl-theme';
    const html = document.documentElement;
    try {
      const stored = localStorage.getItem(KEY);
      if (stored === 'light' || stored === 'dark') html.setAttribute('data-theme', stored);
    } catch {}
    const btn = document.getElementById('themeToggle');
    if (btn) btn.addEventListener('click', () => {
      const isDark = html.getAttribute('data-theme') === 'dark'
        || (!html.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
      const next = isDark ? 'light' : 'dark';
      html.setAttribute('data-theme', next);
      try { localStorage.setItem(KEY, next); } catch {}
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
})();
