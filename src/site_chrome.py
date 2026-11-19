"""One look for every page of the site: the shared fonts, logo and top menu.

Used by the control panel (app.py) and the results dashboard (export_site.py); the landing page
(signal-engine-landing/index.html) carries the same menu in its own markup.

Routes of the single site:
  /            landing page
  /dashboard   results dashboard (static, from export_site.py)
  /app         control panel overview (and /run, /companies, /review, /drafts, /loop)
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1'
         '&family=Schibsted+Grotesk:wght@400..700&display=swap" rel="stylesheet">')

SANS = '"Schibsted Grotesk",system-ui,-apple-system,"Segoe UI",sans-serif'

REPO = "https://github.com/AyushSarkar07/sprinto-signal-engine"

MARK = ('<svg class="sb-mark" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" '
        'd="M2.5 21.5V12a9.5 9.5 0 0 1 19 0v9.5h-6V12a3.5 3.5 0 0 0-7 0v9.5z"/></svg>')

FAVICON = '<link rel="icon" href="/favicon.svg" type="image/svg+xml">'

LINKS = [("home", "Home", "/"), ("results", "Results", "/dashboard"), ("panel", "Control panel", "/app")]

CSS = """
.sitebar{position:sticky;top:0;z-index:50;height:60px;background:#f2f4ee;color:#1c211b;border-bottom:1px solid #dce0d4;
  font-family:"Schibsted Grotesk",system-ui,sans-serif}
.sitebar .sb-in{max-width:1328px;height:100%;margin:0 auto;padding:0 24px;display:flex;align-items:center;gap:24px}
.sitebar a{color:inherit;text-decoration:none}
.sb-logo{display:flex;align-items:center;gap:9px;font-weight:600;font-size:16px;letter-spacing:-.01em;flex:none}
.sb-mark{width:20px;height:20px}
.sb-links{display:flex;gap:4px;margin:0 auto}
.sb-links a{padding:7px 12px;border-radius:999px;font-size:14.5px;color:#5a6157;transition:background .15s,color .15s}
.sb-links a:hover{color:#1c211b;background:rgba(28,33,27,.06)}
.sb-links a[aria-current]{color:#1c211b;font-weight:600;background:rgba(28,33,27,.08)}
.sb-act{flex:none;display:inline-flex;align-items:center;height:38px;padding:0 16px;border-radius:999px;background:#1c211b;color:#f2f4ee!important;
  font-size:14px;font-weight:600;transition:transform .15s}
.sb-act:hover{transform:translateY(-1px)}.sb-act:active{transform:translateY(0) scale(.98)}
.sitebar :focus-visible{outline:2px solid #1c211b;outline-offset:2px}
@media (max-width:760px){.sitebar{height:auto}.sitebar .sb-in{flex-wrap:wrap;gap:8px 12px;padding:10px 16px}
  .sb-links{order:3;margin:0;width:100%;overflow-x:auto}.sb-links a{white-space:nowrap;padding:6px 10px}.sb-act{margin-left:auto;height:34px;padding:0 13px;font-size:13px}}
"""


def sitebar(active: str) -> str:
    links = "".join(f'<a href="{href}"{" aria-current=page" if key == active else ""}>{label}</a>' for key, label, href in LINKS)
    links += f'<a href="{REPO}">Code</a>'
    return (f'<header class="sitebar"><div class="sb-in"><a class="sb-logo" href="/">{MARK}Signal Engine</a>'
            f'<nav class="sb-links" aria-label="Site">{links}</nav><a class="sb-act" href="/run">Research a company</a></div></header>')
