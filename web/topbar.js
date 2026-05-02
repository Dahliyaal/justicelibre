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
</header>`.trim();

  // ─── CSS du header ────────────────────────────────────────────────────
  const TOPBAR_CSS = `
.topbar{
  position:sticky;top:0;z-index:100;
  background:rgba(255,255,255,.96);backdrop-filter:blur(8px);
  display:flex;align-items:center;justify-content:space-between;
  padding:.85rem 2.5rem;
  border-bottom:1px solid var(--line);
}
html[data-theme="dark"] .topbar{background:rgba(34,34,34,.96)}
@media(prefers-color-scheme:dark){html:not([data-theme="light"]) .topbar{background:rgba(34,34,34,.96)}}
.topbar .logo-area{display:flex;align-items:center;gap:.8rem;color:var(--ink)}
.topbar .logo-area:hover{text-decoration:none}
.topbar .logo-area img,.topbar .logo-area svg{width:44px;height:44px}
.topbar .logo-area .name{font-family:var(--display);font-size:1.1rem;color:var(--ink)}
.topbar .logo-area .name .tld{color:var(--teal)}
.topbar .proto-badge{
  display:inline-block;margin-left:.65rem;
  font-size:.58rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;
  padding:.18rem .45rem;border:1px solid var(--gold);color:var(--gold);
  border-radius:2px;vertical-align:middle;cursor:help;
}
.topbar nav.main-nav{display:flex;align-items:center;gap:2rem}
.topbar nav.main-nav a{
  font-size:.78rem;font-weight:600;text-transform:uppercase;letter-spacing:.12em;
  color:var(--ink);padding-bottom:.4rem;border-bottom:3px solid transparent;
  text-decoration:none;
}
.topbar nav.main-nav a.active{color:var(--teal);border-bottom-color:var(--teal)}
.topbar nav.main-nav a:hover{border-bottom-color:var(--teal);text-decoration:none}
@media(max-width:860px){.topbar nav.main-nav a:not(.active){display:none}}
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
.topbar .theme-toggle:hover{color:var(--teal);border-color:var(--teal)}`;

  // ─── Injection ────────────────────────────────────────────────────────
  function inject() {
    // CSS dans le <head>
    if (!document.querySelector('style[data-topbar-injected]')) {
      const style = document.createElement('style');
      style.setAttribute('data-topbar-injected', '1');
      style.textContent = TOPBAR_CSS;
      document.head.appendChild(style);
    }
    // HTML : insère au début du <body>, AVANT tout autre contenu
    const mount = document.querySelector('[data-topbar-mount]');
    if (mount) {
      mount.outerHTML = TOPBAR_HTML;
    } else if (!document.querySelector('header.topbar')) {
      document.body.insertAdjacentHTML('afterbegin', TOPBAR_HTML);
    }

    // Active la nav courante
    const path = location.pathname;
    document.querySelectorAll('header.topbar nav.main-nav a[data-route]').forEach(a => {
      const route = a.getAttribute('data-route');
      if (route === path || (path === '/' && route === '/') ||
          (path.endsWith('/search.html') && route === '/search.html') ||
          (path.endsWith('/ressources.html') && route === '/ressources.html')) {
        a.classList.add('active');
      }
    });

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
