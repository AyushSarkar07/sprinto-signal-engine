"""Signal Engine's own design system: one look for every page, and a Tune panel to customise it.

The look is an instrument panel: a dark ground, one phosphor accent, a wide grotesk for headlines and a mono
face for every reading (quotes, numbers, labels). Visitors can tune it, and the choice follows them across
the site (stored in their browser only):

  data-mode    dark | light
  data-accent  amber | signal | cobalt | lime
  data-head    wide | narrow | serif          (headline style)
  data-motion  on | off                       (off also when the OS asks for reduced motion)

Routes of the single site:
  /            home (src/site_home.py, drawn from the real research results)
  /dashboard   results dashboard (static, from export_site.py)
  /app         control panel overview (and /run, /companies, /review, /drafts, /loop)
  /theme.css, /theme.js, /favicon.svg   served by app.py from this module
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,300..900'
         '&family=IBM+Plex+Mono:wght@400;500;600&family=Instrument+Serif&display=swap" rel="stylesheet">')

SANS = '"Archivo",system-ui,-apple-system,"Segoe UI",sans-serif'
MONO = '"IBM Plex Mono",ui-monospace,"SFMono-Regular",Menlo,monospace'

REPO = "https://github.com/AyushSarkar07/sprinto-signal-engine"

# the mark: a square scope with one pulse running through it
MARK = ('<svg class="sb-mark" viewBox="0 0 24 24" aria-hidden="true"><rect x="1" y="1" width="22" height="22" rx="5" fill="currentColor"/>'
        '<path d="M4 13h4l2-6 3 10 2-5h5" fill="none" stroke="var(--accent)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>')

FAVICON_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect x="1" y="1" width="22" height="22" rx="5" fill="#0c0d0c"/>'
               '<path d="M4 13h4l2-6 3 10 2-5h5" fill="none" stroke="#ffb224" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
FAVICON = '<link rel="icon" href="/favicon.svg" type="image/svg+xml">'

LINKS = [("home", "Home", "/"), ("results", "Results", "/dashboard"), ("panel", "Control panel", "/app")]

# Applied before first paint so a saved theme never flashes the default.
HEAD_JS = """<script>(function(){var d=document.documentElement,p={};try{p=JSON.parse(localStorage.getItem('se-theme')||'{}')}catch(e){}
var rm=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
d.dataset.mode=p.mode||'dark';d.dataset.accent=p.accent||'amber';d.dataset.head=p.head||'wide';d.dataset.motion=p.motion||(rm?'off':'on');})()</script>"""

HEAD = FONTS + FAVICON + '<link rel="stylesheet" href="/theme.css">' + HEAD_JS

THEME_CSS = r"""
/* ---------- tokens ---------- */
html[data-mode]{--bg:#0c0d0c;--surface:#151715;--surface-2:#1d201d;--ink:#eef0ea;--muted:#9da394;--line:#2b2f2a;--panel:#070807;--panel-ink:#eef0ea;
  --go:#7fe0a6;--go-bg:#11281b;--flag:#f3c968;--flag-bg:#2f250e;--hold:#a9b8f0;--hold-bg:#1a2036;--stop:#f59d8b;--stop-bg:#341611;
  --sans:"Archivo",system-ui,-apple-system,"Segoe UI",sans-serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
  --radius:14px;color-scheme:dark}
html[data-mode="light"]{--bg:#f3f3ef;--surface:#ffffff;--surface-2:#e9e9e3;--ink:#111311;--muted:#585d55;--line:#d6d7cf;--panel:#111311;--panel-ink:#eef0ea;
  --go:#1d6b45;--go-bg:#e1efe6;--flag:#7d5200;--flag-bg:#f6ebd0;--hold:#34468c;--hold-bg:#e5e8f5;--stop:#9b2c1f;--stop-bg:#f6e1dc;color-scheme:light}
html[data-accent="amber"]{--accent:#ffb224;--accent-ink:#1a1200;--accent-text:#ffb224}
html[data-accent="signal"]{--accent:#3ee08f;--accent-ink:#03140a;--accent-text:#3ee08f}
html[data-accent="cobalt"]{--accent:#7b96ff;--accent-ink:#060c27;--accent-text:#8fa6ff}
html[data-accent="lime"]{--accent:#d4ff3f;--accent-ink:#141a00;--accent-text:#d4ff3f}
html[data-mode="light"][data-accent="amber"]{--accent-text:#9a5800}
html[data-mode="light"][data-accent="signal"]{--accent-text:#0b7442}
html[data-mode="light"][data-accent="cobalt"]{--accent-text:#2a48c9}
html[data-mode="light"][data-accent="lime"]{--accent-text:#4a6600}
html[data-head="wide"]{--display:"Archivo",system-ui,sans-serif;--dw:760;--ds:125%;--dt:-.035em;--dl:.94;--dc:none}
html[data-head="narrow"]{--display:"Archivo",system-ui,sans-serif;--dw:800;--ds:62%;--dt:-.005em;--dl:.9;--dc:uppercase}
html[data-head="serif"]{--display:"Instrument Serif",Georgia,serif;--dw:400;--ds:100%;--dt:-.015em;--dl:.98;--dc:none}

/* the panel and the results page speak in these names; map them onto the tokens */
html[data-mode]{--paper:var(--bg);--card:var(--surface);--soft:var(--muted);--lime:var(--accent);--limeink:var(--accent-ink);
  --side:var(--panel);--sideink:var(--panel-ink);--serif:var(--display);
  --gobg:var(--go-bg);--flagbg:var(--flag-bg);--holdbg:var(--hold-bg);--stopbg:var(--stop-bg)}
html[data-mode] body{background:var(--bg);color:var(--ink);font-family:var(--sans)}
html[data-mode] ::selection{background:var(--accent);color:var(--accent-ink)}
html[data-head] :is(h1,h2){font-family:var(--display);font-weight:var(--dw);font-stretch:var(--ds);letter-spacing:var(--dt);text-transform:var(--dc)}
html[data-head] h1{line-height:var(--dl)}
html[data-mode] :is(h1,h2,h3){text-wrap:balance}html[data-mode] :is(p,li,blockquote){text-wrap:pretty}
html[data-head] :is(h1,h2) em{font-family:inherit;font-style:normal;color:var(--accent-text)}
html[data-mode] :focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* ---------- the site bar ---------- */
.sitebar{position:sticky;top:0;z-index:60;height:60px;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(12px);
  -webkit-backdrop-filter:blur(12px);color:var(--ink);border-bottom:1px solid var(--line);font-family:var(--sans)}
.sitebar .sb-in{max-width:1328px;height:100%;margin:0 auto;padding:0 24px;display:flex;align-items:center;gap:20px}
.sitebar a{color:inherit;text-decoration:none}
.sb-logo{display:flex;align-items:center;gap:10px;font-weight:720;font-stretch:118%;font-size:15px;letter-spacing:-.01em;flex:none}
.sb-mark{width:24px;height:24px;color:var(--ink)}
.sb-links{display:flex;gap:2px;margin:0 auto;font-family:var(--mono);font-size:13px;text-transform:uppercase;letter-spacing:.06em}
.sb-links a{padding:8px 12px;border-radius:8px;color:var(--muted);transition:color .15s,background .15s}
.sb-links a:hover{color:var(--ink);background:var(--surface-2)}
.sb-links a[aria-current]{color:var(--ink)}
.sb-links a[aria-current]::before{content:"";display:inline-block;width:7px;height:7px;border-radius:2px;background:var(--accent);margin-right:8px;vertical-align:1px}
.sb-tune{flex:none;display:inline-flex;align-items:center;gap:8px;height:38px;padding:0 14px;border-radius:10px;border:1px solid var(--line);
  background:var(--surface);color:var(--ink);font:500 13px var(--mono);text-transform:uppercase;letter-spacing:.06em;cursor:pointer}
.sb-tune:hover{border-color:var(--ink)}.sb-tune svg{width:16px;height:16px}
.sb-act{flex:none;display:inline-flex;align-items:center;height:38px;padding:0 16px;border-radius:10px;background:var(--accent);color:var(--accent-ink)!important;
  font-weight:700;font-size:14px;transition:transform .15s}
.sb-act:hover{transform:translateY(-1px)}.sb-act:active{transform:translateY(0) scale(.98)}
@media (max-width:820px){.sitebar{height:auto}.sitebar .sb-in{flex-wrap:wrap;gap:8px 10px;padding:10px 16px}
  .sb-links{order:3;margin:0;width:100%;overflow-x:auto}.sb-links a{white-space:nowrap;padding:6px 9px}
  .sb-tune{margin-left:auto;height:34px;padding:0 10px}.sb-act{height:34px;padding:0 12px;font-size:13px}}
@media (max-width:420px){.sb-act span{display:none}}

/* ---------- the Tune panel ---------- */
.tune{position:fixed;z-index:70;top:68px;right:max(16px,calc((100vw - 1328px)/2 + 24px));width:min(340px,calc(100vw - 32px));
  background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 24px 60px rgba(0,0,0,.35);
  font-family:var(--sans)}
.tune[hidden]{display:none}
.tune .tune-h{font:600 12px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 14px;
  display:flex;justify-content:space-between;align-items:center}
.tune .tune-h button{background:none;border:0;color:var(--muted);font:inherit;cursor:pointer;padding:4px}
.tune fieldset{border:0;padding:0;margin:0 0 16px}.tune legend{font-size:13px;font-weight:600;margin-bottom:8px;padding:0}
.tune .opts{display:flex;gap:6px;flex-wrap:wrap}
.tune .opt{flex:1;min-width:0;height:36px;border-radius:9px;border:1px solid var(--line);background:var(--surface-2);color:var(--ink);
  font:500 13px var(--sans);cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:7px}
.tune .opt[aria-pressed="true"]{border-color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink)}
.tune .sw{width:14px;height:14px;border-radius:4px;flex:none}
.tune .opt.h-wide{font-stretch:125%;font-weight:760}.tune .opt.h-narrow{font-stretch:62%;font-weight:800;text-transform:uppercase}
.tune .opt.h-serif{font-family:"Instrument Serif",serif;font-size:16px}
.tune .reset{width:100%;height:36px;border-radius:9px;border:1px dashed var(--line);background:none;color:var(--muted);font:500 12px var(--mono);
  text-transform:uppercase;letter-spacing:.06em;cursor:pointer}
html[data-motion="off"] *,html[data-motion="off"] *::before,html[data-motion="off"] *::after{animation:none!important;transition:none!important}
"""

THEME_JS = r"""
(function(){
  var d=document.documentElement, KEY='se-theme';
  var defaults={mode:'dark',accent:'amber',head:'wide',motion:(matchMedia('(prefers-reduced-motion: reduce)').matches?'off':'on')};
  function read(){try{return Object.assign({},defaults,JSON.parse(localStorage.getItem(KEY)||'{}'))}catch(e){return Object.assign({},defaults)}}
  function save(p){try{localStorage.setItem(KEY,JSON.stringify(p))}catch(e){}}
  var groups=[
    ['accent','Accent',[['amber','Amber','#ffb224'],['signal','Signal','#3ee08f'],['cobalt','Cobalt','#7b96ff'],['lime','Lime','#d4ff3f']]],
    ['mode','Ground',[['dark','Dark'],['light','Light']]],
    ['head','Headlines',[['wide','Wide'],['narrow','Narrow'],['serif','Serif']]],
    ['motion','Motion',[['on','On'],['off','Still']]]];
  var panel=document.createElement('div');panel.className='tune';panel.id='tune';panel.hidden=true;
  panel.setAttribute('role','dialog');panel.setAttribute('aria-label','Tune the look');
  var h='<p class="tune-h">Tune the look <button type="button" data-close>Close</button></p>';
  groups.forEach(function(g){h+='<fieldset><legend>'+g[1]+'</legend><div class="opts">';
    g[2].forEach(function(o){h+='<button type="button" class="opt '+(g[0]==='head'?'h-'+o[0]:'')+'" data-k="'+g[0]+'" data-v="'+o[0]+'" aria-pressed="false">'+
      (o[2]?'<span class="sw" style="background:'+o[2]+'"></span>':'')+o[1]+'</button>'});h+='</div></fieldset>'});
  h+='<button type="button" class="reset" data-reset>Back to default</button>';panel.innerHTML=h;
  function sync(p){panel.querySelectorAll('.opt').forEach(function(b){b.setAttribute('aria-pressed',String(p[b.dataset.k]===b.dataset.v))})}
  function apply(p){for(var k in p)d.dataset[k]=p[k];sync(p);document.dispatchEvent(new CustomEvent('se-theme',{detail:p}))}
  function boot(){
    document.body.appendChild(panel);var p=read();apply(p);
    var btn=document.querySelector('[data-tune]');
    function open(v){panel.hidden=!v;if(btn)btn.setAttribute('aria-expanded',String(v));if(v){var f=panel.querySelector('[aria-pressed="true"]');f&&f.focus()}else if(btn){btn.focus()}}
    if(btn)btn.addEventListener('click',function(e){e.stopPropagation();open(panel.hidden)});
    panel.addEventListener('click',function(e){var t=e.target.closest('button');if(!t)return;
      if(t.hasAttribute('data-close'))return open(false);
      if(t.hasAttribute('data-reset')){p=Object.assign({},defaults);try{localStorage.removeItem(KEY)}catch(_){}apply(p);return}
      p[t.dataset.k]=t.dataset.v;save(p);apply(p)});
    document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!panel.hidden)open(false)});
    document.addEventListener('click',function(e){if(!panel.hidden&&!panel.contains(e.target))open(false)});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
"""

TUNE_ICON = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">'
             '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/></svg>')


def sitebar(active: str) -> str:
    links = "".join(f'<a href="{href}"{" aria-current=page" if key == active else ""}>{label}</a>' for key, label, href in LINKS)
    links += f'<a href="{REPO}">Code</a>'
    return (f'<header class="sitebar"><div class="sb-in"><a class="sb-logo" href="/">{MARK}Signal Engine</a>'
            f'<nav class="sb-links" aria-label="Site">{links}</nav>'
            f'<button class="sb-tune" type="button" data-tune aria-controls="tune" aria-expanded="false">{TUNE_ICON}Tune</button>'
            f'<a class="sb-act" href="/run">Research<span>&nbsp;a company</span></a></div></header>'
            '<script src="/theme.js" defer></script>')
