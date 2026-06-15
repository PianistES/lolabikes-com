#!/usr/bin/env python3
"""
Lola Bikes — Blog Generator
Haalt gepubliceerde blogposts op uit Contentful, vertaalt ze naar alle 7 talen
via de Anthropic API, en genereert per taal een aparte HTML-pagina met eigen URL.

Gebruik: python scripts/generate_blog.py
"""

import os, json, re, sys, datetime
import urllib.request, urllib.parse

# ─── CONFIG ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]
CONTENTFUL_SPACE    = os.environ["CONTENTFUL_SPACE_ID"]
CONTENTFUL_CDA_KEY  = os.environ["CONTENTFUL_CDA_TOKEN"]   # Content Delivery API
CONTENTFUL_CMA_KEY  = os.environ["CONTENTFUL_CMA_TOKEN"]   # Content Management API
SITE_URL            = "https://lolabikes.com"

LANGUAGES = {
    "es": {"name": "Español",     "url_prefix": "",      "label": "Spanish"},
    "nl": {"name": "Nederlands",  "url_prefix": "/nl",   "label": "Dutch"},
    "en": {"name": "English",     "url_prefix": "/en",   "label": "English"},
    "fr": {"name": "Français",    "url_prefix": "/fr",   "label": "French"},
    "de": {"name": "Deutsch",     "url_prefix": "/de",   "label": "German"},
    "it": {"name": "Italiano",    "url_prefix": "/it",   "label": "Italian"},
    "ru": {"name": "Русский",     "url_prefix": "/ru",   "label": "Russian"},
}

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def api_call(url, headers, data=None, method="GET"):
    req = urllib.request.Request(url, headers=headers, method=method)
    if data:
        req.data = json.dumps(data).encode()
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def contentful_get(path):
    url = f"https://cdn.contentful.com/spaces/{CONTENTFUL_SPACE}{path}"
    headers = {"Authorization": f"Bearer {CONTENTFUL_CDA_KEY}"}
    return api_call(url, headers)

def contentful_update(entry_id, field, value):
    """Update a single field in a Contentful entry via CMA."""
    url = f"https://api.contentful.com/spaces/{CONTENTFUL_SPACE}/entries/{entry_id}"
    headers = {
        "Authorization": f"Bearer {CONTENTFUL_CMA_KEY}",
        "Content-Type": "application/vnd.contentful.management.v1+json",
        "X-Contentful-Version": "0",  # Will be overwritten per call
    }
    # Get current version first
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {CONTENTFUL_CMA_KEY}",
    })
    with urllib.request.urlopen(req) as r:
        entry = json.loads(r.read())
    version = entry["sys"]["version"]
    entry["fields"][field] = value
    headers["X-Contentful-Version"] = str(version)
    return api_call(url, headers, entry, method="PUT")

def anthropic_translate(nl_title, nl_content, nl_excerpt, image_url):
    """Ask Claude to translate the blog into all 7 languages + create SEO data."""
    prompt = f"""You are translating a Dutch blog post for Lola Bikes Málaga, a family bike rental company.
They rent Urban Arrow electric cargo bikes (€75/day) and City Bikes (€15/day) with delivery within 8km of Málaga.
Brand tone: warm, playful, local, simple. Never use jargon.

Dutch title: {nl_title}
Dutch excerpt: {nl_excerpt}
Dutch content (HTML rich text):
{nl_content}

Translate this blog post into these 7 languages. For EACH language provide:
1. "title" — SEO-optimised title (60 chars max), natural in that language
2. "slug" — URL-friendly slug in that language (lowercase, hyphens, no accents, 50 chars max)
3. "excerpt" — Meta description / excerpt (155 chars max)
4. "meta_keywords" — 5-7 SEO keywords comma-separated
5. "content" — Full blog translation as clean HTML (use <h2>, <h3>, <p>, <ul>, <li>, <a href> tags, preserve all links from the Dutch version)

Languages: es (Spanish), nl (Dutch — keep as-is but clean up any typos), en (English), fr (French), de (German), it (Italian), ru (Russian)

Return ONLY valid JSON, no markdown fences, in this exact structure:
{{
  "es": {{"title":"...","slug":"...","excerpt":"...","meta_keywords":"...","content":"..."}},
  "nl": {{"title":"...","slug":"...","excerpt":"...","meta_keywords":"...","content":"..."}},
  "en": {{"title":"...","slug":"...","excerpt":"...","meta_keywords":"...","content":"..."}},
  "fr": {{"title":"...","slug":"...","excerpt":"...","meta_keywords":"...","content":"..."}},
  "de": {{"title":"...","slug":"...","excerpt":"...","meta_keywords":"...","content":"..."}},
  "it": {{"title":"...","slug":"...","excerpt":"...","meta_keywords":"...","content":"..."}},
  "ru": {{"title":"...","slug":"...","excerpt":"...","meta_keywords":"...","content":"..."}}
}}"""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": prompt}],
    }
    result = api_call("https://api.anthropic.com/v1/messages", headers, body, "POST")
    raw = result["content"][0]["text"].strip()
    # Strip any accidental markdown fences
    raw = re.sub(r"^```json\s*|^```\s*|```$", "", raw, flags=re.MULTILINE).strip()
    return json.loads(raw)

def richtext_to_html(node):
    """Convert Contentful Rich Text JSON to HTML."""
    if not node:
        return ""
    ntype = node.get("nodeType", "")
    content = node.get("content", [])

    def children(nodes):
        return "".join(richtext_to_html(n) for n in nodes)

    if ntype == "document":
        return children(content)
    elif ntype == "paragraph":
        inner = children(content)
        return f"<p>{inner}</p>\n" if inner.strip() else ""
    elif ntype == "heading-1":
        return f"<h1>{children(content)}</h1>\n"
    elif ntype == "heading-2":
        return f"<h2>{children(content)}</h2>\n"
    elif ntype == "heading-3":
        return f"<h3>{children(content)}</h3>\n"
    elif ntype == "heading-4":
        return f"<h4>{children(content)}</h4>\n"
    elif ntype == "unordered-list":
        return f"<ul>\n{children(content)}</ul>\n"
    elif ntype == "ordered-list":
        return f"<ol>\n{children(content)}</ol>\n"
    elif ntype == "list-item":
        return f"<li>{children(content)}</li>\n"
    elif ntype == "blockquote":
        return f"<blockquote>{children(content)}</blockquote>\n"
    elif ntype == "hr":
        return "<hr>\n"
    elif ntype == "hyperlink":
        href = node.get("data", {}).get("uri", "#")
        return f'<a href="{href}" target="_blank" rel="noopener">{children(content)}</a>'
    elif ntype == "text":
        text = node.get("value", "")
        marks = [m["type"] for m in node.get("marks", [])]
        if "bold" in marks:
            text = f"<strong>{text}</strong>"
        if "italic" in marks:
            text = f"<em>{text}</em>"
        if "underline" in marks:
            text = f"<u>{text}</u>"
        if "code" in marks:
            text = f"<code>{text}</code>"
        return text
    elif ntype == "embedded-asset-block":
        asset_id = node.get("data", {}).get("target", {}).get("sys", {}).get("id", "")
        return f'<!-- embedded asset {asset_id} -->'
    else:
        return children(content)

def generate_html_page(lang, lang_data, translations, image_url, pub_date, all_slugs):
    """Generate a complete HTML blog page for one language."""
    cfg      = LANGUAGES[lang]
    prefix   = cfg["url_prefix"]
    t        = translations[lang]
    title    = t["title"]
    slug     = t["slug"]
    excerpt  = t["excerpt"]
    keywords = t["meta_keywords"]
    content  = t["content"]

    # Hreflang tags
    hreflang_tags = ""
    for l, info in LANGUAGES.items():
        l_slug  = all_slugs[l]
        l_prefix = info["url_prefix"]
        url = f"{SITE_URL}{l_prefix}/blog/{l_slug}/"
        hreflang_tags += f'    <link rel="alternate" hreflang="{l}" href="{url}">\n'
    hreflang_tags += f'    <link rel="alternate" hreflang="x-default" href="{SITE_URL}/blog/{all_slugs["es"]}/">\n'

    # Language switcher
    lang_links = ""
    for l, info in LANGUAGES.items():
        active = ' class="active"' if l == lang else ""
        l_slug = all_slugs[l]
        l_prefix = info["url_prefix"]
        url = f"{l_prefix}/blog/{l_slug}/"
        lang_links += f'<a href="{url}"{active}>{info["name"]}</a>\n'

    # Nav links
    home_url = prefix + "/"
    blog_url = prefix + "/blog/"

    pub_formatted = ""
    if pub_date:
        try:
            d = datetime.datetime.strptime(pub_date[:10], "%Y-%m-%d")
            pub_formatted = d.strftime("%-d %B %Y")
        except:
            pub_formatted = pub_date[:10]

    img_tag = ""
    if image_url:
        img_tag = f'<img src="{image_url}" alt="{title}" class="hero-image" loading="eager">'

    canonical = f"{SITE_URL}{prefix}/blog/{slug}/"

    html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | Lola Bikes Málaga</title>
  <meta name="description" content="{excerpt}">
  <meta name="keywords" content="{keywords}">
  <link rel="canonical" href="{canonical}">

  <!-- Open Graph -->
  <meta property="og:type" content="article">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{excerpt}">
  <meta property="og:url" content="{canonical}">
  {'<meta property="og:image" content="' + image_url + '">' if image_url else ''}
  <meta property="og:site_name" content="Lola Bikes Málaga">

  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{excerpt}">
  {'<meta name="twitter:image" content="' + image_url + '">' if image_url else ''}

  <!-- Hreflang -->
{hreflang_tags}
  <!-- Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Barlow:ital,wght@0,300;0,400;0,600;0,700;0,800&family=Barlow+Condensed:wght@700;800;900&display=swap" rel="stylesheet">

  <!-- Schema.org Article -->
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    "headline": "{title}",
    "description": "{excerpt}",
    "image": "{image_url}",
    "datePublished": "{pub_date[:10] if pub_date else ''}",
    "publisher": {{
      "@type": "Organization",
      "name": "Lola Bikes Málaga",
      "url": "{SITE_URL}"
    }},
    "mainEntityOfPage": "{canonical}"
  }}
  </script>

  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --ink:   #1C1A17;
      --terra: #C85A20;
      --cream: #F4EEE4;
      --sand:  #E2D0B0;
      --clay:  #A07050;
      --smoke: #2B2825;
    }}

    body {{
      font-family: 'Barlow', sans-serif;
      background: var(--cream);
      color: var(--ink);
      line-height: 1.7;
    }}

    /* ── NAV ── */
    nav {{
      background: var(--smoke);
      padding: 0 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      height: 64px;
      position: sticky;
      top: 0;
      z-index: 100;
    }}
    .nav-logo {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 900;
      font-size: 22px;
      color: var(--cream);
      text-decoration: none;
      letter-spacing: 2px;
      text-transform: uppercase;
    }}
    .nav-logo span {{ color: var(--terra); }}
    .nav-links {{ display: flex; gap: 28px; align-items: center; }}
    .nav-links a {{
      color: rgba(244,238,228,0.7);
      text-decoration: none;
      font-size: 13px;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      font-weight: 600;
      transition: color 0.2s;
    }}
    .nav-links a:hover {{ color: var(--cream); }}

    /* ── LANG SWITCHER ── */
    .lang-bar {{
      background: var(--sand);
      padding: 8px 24px;
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      align-items: center;
      font-size: 12px;
    }}
    .lang-bar a {{
      color: var(--ink);
      text-decoration: none;
      opacity: 0.5;
      font-weight: 600;
      letter-spacing: 1px;
      transition: opacity 0.2s;
    }}
    .lang-bar a:hover, .lang-bar a.active {{
      opacity: 1;
      color: var(--terra);
    }}

    /* ── HERO IMAGE ── */
    .hero-image {{
      width: 100%;
      max-height: 480px;
      object-fit: cover;
      display: block;
    }}

    /* ── ARTICLE ── */
    .article-wrap {{
      max-width: 760px;
      margin: 0 auto;
      padding: 48px 24px 80px;
    }}

    .article-meta {{
      font-size: 12px;
      letter-spacing: 2px;
      text-transform: uppercase;
      color: var(--terra);
      font-weight: 700;
      margin-bottom: 16px;
    }}

    .article-title {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 900;
      font-size: clamp(32px, 5vw, 52px);
      line-height: 1.05;
      color: var(--ink);
      text-transform: uppercase;
      letter-spacing: -0.5px;
      margin-bottom: 24px;
    }}

    .article-excerpt {{
      font-size: 18px;
      font-weight: 300;
      color: var(--ink);
      opacity: 0.7;
      line-height: 1.6;
      margin-bottom: 40px;
      padding-bottom: 40px;
      border-bottom: 1px solid var(--sand);
    }}

    /* ── RICH TEXT CONTENT ── */
    .article-content h2 {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 800;
      font-size: 28px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--ink);
      margin: 40px 0 16px;
    }}
    .article-content h3 {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700;
      font-size: 22px;
      text-transform: uppercase;
      color: var(--terra);
      margin: 32px 0 12px;
    }}
    .article-content h4 {{
      font-weight: 700;
      font-size: 16px;
      margin: 24px 0 8px;
    }}
    .article-content p {{
      margin-bottom: 20px;
      font-size: 17px;
      line-height: 1.75;
    }}
    .article-content ul, .article-content ol {{
      margin: 0 0 20px 24px;
    }}
    .article-content li {{
      margin-bottom: 8px;
      font-size: 17px;
      line-height: 1.6;
    }}
    .article-content a {{
      color: var(--terra);
      text-decoration: underline;
      text-underline-offset: 3px;
    }}
    .article-content a:hover {{ opacity: 0.75; }}
    .article-content blockquote {{
      border-left: 3px solid var(--terra);
      padding: 16px 24px;
      margin: 24px 0;
      background: var(--sand);
      font-style: italic;
      font-size: 18px;
      line-height: 1.6;
    }}
    .article-content strong {{ font-weight: 700; }}
    .article-content em {{ font-style: italic; }}
    .article-content hr {{
      border: none;
      border-top: 1px solid var(--sand);
      margin: 40px 0;
    }}
    .article-content code {{
      background: var(--sand);
      padding: 2px 6px;
      border-radius: 3px;
      font-family: monospace;
      font-size: 14px;
    }}

    /* ── CTA ── */
    .cta-block {{
      background: var(--smoke);
      border-radius: 6px;
      padding: 40px;
      text-align: center;
      margin-top: 56px;
    }}
    .cta-block h3 {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 900;
      font-size: 28px;
      text-transform: uppercase;
      color: var(--cream);
      margin-bottom: 12px;
    }}
    .cta-block p {{
      color: rgba(244,238,228,0.65);
      margin-bottom: 24px;
      font-size: 16px;
    }}
    .cta-btn {{
      display: inline-block;
      background: var(--terra);
      color: var(--cream);
      text-decoration: none;
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 800;
      font-size: 16px;
      letter-spacing: 2px;
      text-transform: uppercase;
      padding: 14px 32px;
      border-radius: 3px;
      transition: opacity 0.2s;
    }}
    .cta-btn:hover {{ opacity: 0.85; }}

    /* ── BACK LINK ── */
    .back-link {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--clay);
      text-decoration: none;
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      margin-bottom: 32px;
    }}
    .back-link:hover {{ color: var(--terra); }}

    /* ── FOOTER ── */
    footer {{
      background: var(--smoke);
      color: rgba(244,238,228,0.5);
      text-align: center;
      padding: 32px 24px;
      font-size: 13px;
    }}
    footer a {{ color: var(--terra); text-decoration: none; }}

    @media (max-width: 640px) {{
      .nav-links {{ display: none; }}
      .article-wrap {{ padding: 32px 16px 60px; }}
      .cta-block {{ padding: 28px 20px; }}
    }}
  </style>
</head>
<body>

<nav>
  <a href="{home_url}" class="nav-logo">LOLA <span>BIKES</span></a>
  <div class="nav-links">
    <a href="{home_url}">Home</a>
    <a href="{home_url}#bikes">Bikes</a>
    <a href="{home_url}#booking">Booking</a>
    <a href="{blog_url}">Blog</a>
  </div>
</nav>

<div class="lang-bar">
{lang_links}
</div>

{img_tag}

<div class="article-wrap">
  <a href="{blog_url}" class="back-link">← Blog</a>

  <div class="article-meta">Lola Bikes Málaga · {pub_formatted}</div>
  <h1 class="article-title">{title}</h1>
  <p class="article-excerpt">{excerpt}</p>

  <div class="article-content">
    {content}
  </div>

  <div class="cta-block">
    <h3>Ready to ride?</h3>
    <p>Book your bike for Málaga — delivery included.</p>
    <a href="{home_url}#booking" class="cta-btn">Book Now →</a>
  </div>
</div>

<footer>
  <p>© 2025 Lola Bikes Málaga · <a href="mailto:hello@lolabikes.com">hello@lolabikes.com</a> · <a href="https://wa.me/34711226882">WhatsApp</a></p>
</footer>

</body>
</html>"""
    return slug, html

# ─── BLOG INDEX PAGE ─────────────────────────────────────────────────────────
def generate_blog_index(lang, posts_data):
    """Generate the blog overview page for a language."""
    cfg    = LANGUAGES[lang]
    prefix = cfg["url_prefix"]

    labels = {
        "es": {"title": "Blog", "subtitle": "Consejos, rutas y todo sobre bicicletas en Málaga", "read": "Leer más →"},
        "nl": {"title": "Blog", "subtitle": "Tips, routes en alles over fietsen in Málaga",      "read": "Lees meer →"},
        "en": {"title": "Blog", "subtitle": "Tips, routes and everything about cycling in Málaga","read": "Read more →"},
        "fr": {"title": "Blog", "subtitle": "Conseils, itinéraires et tout sur le vélo à Málaga","read": "Lire la suite →"},
        "de": {"title": "Blog", "subtitle": "Tipps, Routen und alles über Radfahren in Málaga",  "read": "Mehr lesen →"},
        "it": {"title": "Blog", "subtitle": "Consigli, percorsi e tutto sulle bici a Málaga",    "read": "Leggi di più →"},
        "ru": {"title": "Блог","subtitle": "Советы, маршруты и всё о велоспорте в Малаге",       "read": "Читать далее →"},
    }
    lbl = labels[lang]

    cards = ""
    for p in posts_data:
        t = p["translations"][lang]
        slug = t["slug"]
        url  = f"{prefix}/blog/{slug}/"
        img  = p.get("image_url", "")
        img_html = f'<img src="{img}" alt="{t["title"]}" loading="lazy">' if img else '<div class="card-img-placeholder"></div>'
        cards += f"""
    <article class="card">
      <a href="{url}" class="card-img-link">{img_html}</a>
      <div class="card-body">
        <div class="card-date">{p.get("pub_date","")[:10]}</div>
        <h2 class="card-title"><a href="{url}">{t["title"]}</a></h2>
        <p class="card-excerpt">{t["excerpt"]}</p>
        <a href="{url}" class="card-read">{lbl["read"]}</a>
      </div>
    </article>"""

    canonical = f"https://lolabikes.com{prefix}/blog/"
    home_url  = prefix + "/"

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{lbl["title"]} | Lola Bikes Málaga</title>
  <meta name="description" content="{lbl["subtitle"]}">
  <link rel="canonical" href="{canonical}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Barlow:wght@300;400;600;700;800&family=Barlow+Condensed:wght@700;800;900&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing:border-box; margin:0; padding:0; }}
    :root {{ --ink:#1C1A17;--terra:#C85A20;--cream:#F4EEE4;--sand:#E2D0B0;--smoke:#2B2825; }}
    body {{ font-family:'Barlow',sans-serif; background:var(--cream); color:var(--ink); }}
    nav {{ background:var(--smoke); padding:0 24px; display:flex; align-items:center; justify-content:space-between; height:64px; position:sticky; top:0; z-index:100; }}
    .nav-logo {{ font-family:'Barlow Condensed',sans-serif; font-weight:900; font-size:22px; color:var(--cream); text-decoration:none; letter-spacing:2px; text-transform:uppercase; }}
    .nav-logo span {{ color:var(--terra); }}
    .page-hero {{ background:var(--smoke); padding:60px 24px; text-align:center; }}
    .page-hero h1 {{ font-family:'Barlow Condensed',sans-serif; font-weight:900; font-size:56px; color:var(--cream); text-transform:uppercase; letter-spacing:-1px; }}
    .page-hero p {{ color:rgba(244,238,228,0.6); margin-top:12px; font-size:17px; }}
    .blog-grid {{ max-width:1100px; margin:0 auto; padding:56px 24px; display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:32px; }}
    .card {{ background:#fff; border-radius:6px; overflow:hidden; box-shadow:0 2px 12px rgba(28,26,23,0.08); transition:transform 0.2s; }}
    .card:hover {{ transform:translateY(-4px); }}
    .card-img-link img {{ width:100%; height:220px; object-fit:cover; display:block; }}
    .card-img-placeholder {{ width:100%; height:220px; background:var(--sand); }}
    .card-body {{ padding:24px; }}
    .card-date {{ font-size:11px; letter-spacing:2px; text-transform:uppercase; color:var(--terra); font-weight:700; margin-bottom:10px; }}
    .card-title {{ font-family:'Barlow Condensed',sans-serif; font-weight:800; font-size:22px; text-transform:uppercase; margin-bottom:10px; }}
    .card-title a {{ color:var(--ink); text-decoration:none; }}
    .card-title a:hover {{ color:var(--terra); }}
    .card-excerpt {{ font-size:14px; opacity:0.65; line-height:1.65; margin-bottom:16px; }}
    .card-read {{ font-size:12px; font-weight:700; letter-spacing:1.5px; text-transform:uppercase; color:var(--terra); text-decoration:none; }}
    footer {{ background:var(--smoke); color:rgba(244,238,228,0.5); text-align:center; padding:32px 24px; font-size:13px; }}
    footer a {{ color:var(--terra); text-decoration:none; }}
  </style>
</head>
<body>
<nav>
  <a href="{home_url}" class="nav-logo">LOLA <span>BIKES</span></a>
</nav>
<div class="page-hero">
  <h1>{lbl["title"]}</h1>
  <p>{lbl["subtitle"]}</p>
</div>
<div class="blog-grid">
  {cards}
</div>
<footer>
  <p>© 2025 Lola Bikes Málaga · <a href="mailto:hello@lolabikes.com">hello@lolabikes.com</a></p>
</footer>
</body>
</html>"""

# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    print("📡 Fetching published blog posts from Contentful...")
    resp    = contentful_get(f"/environments/master/entries?content_type=blogPost&fields.status=published&include=1")
    entries = resp.get("items", [])
    assets  = {a["sys"]["id"]: a for a in resp.get("includes", {}).get("Asset", [])}

    if not entries:
        print("No published posts found. Exiting.")
        return

    all_posts_data = []

    for entry in entries:
        fields  = entry["fields"]
        entry_id = entry["sys"]["id"]
        nl_title   = fields.get("title", {}).get("nl", fields.get("title", {}).get("en", ""))
        nl_excerpt  = fields.get("excerpt", {}).get("nl", fields.get("excerpt", {}).get("en", ""))
        pub_date   = fields.get("publishDate", {}).get("en", "")
        richtext   = fields.get("content", {}).get("nl", fields.get("content", {}).get("en", {}))
        nl_content = richtext_to_html(richtext) if richtext else ""

        # Image
        image_url = ""
        img_ref = fields.get("featuredImage", {}).get("en", {})
        img_id  = img_ref.get("sys", {}).get("id", "")
        if img_id and img_id in assets:
            file_url = assets[img_id].get("fields", {}).get("file", {}).get("url", "")
            if file_url:
                image_url = "https:" + file_url if file_url.startswith("//") else file_url

        print(f"\n✍️  Translating: {nl_title}")
        try:
            translations = anthropic_translate(nl_title, nl_content, nl_excerpt, image_url)
        except Exception as e:
            print(f"  ❌ Translation failed: {e}")
            continue

        # Collect all slugs for hreflang
        all_slugs = {l: translations[l]["slug"] for l in LANGUAGES}

        # Write HTML files
        for lang in LANGUAGES:
            cfg    = LANGUAGES[lang]
            prefix = cfg["url_prefix"].lstrip("/")
            slug, html = generate_html_page(lang, cfg, translations, image_url, pub_date, all_slugs)

            if prefix:
                out_dir = f"{prefix}/blog/{slug}"
            else:
                out_dir = f"blog/{slug}"

            os.makedirs(out_dir, exist_ok=True)
            with open(f"{out_dir}/index.html", "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  ✅ {lang}: /{out_dir}/")

        all_posts_data.append({
            "translations": translations,
            "image_url": image_url,
            "pub_date": pub_date,
        })

        # Mark as 'generated' in Contentful so we don't regenerate next time
        # (optional — comment out if you prefer to always regenerate)
        # contentful_update(entry_id, "status", {"en": "generated"})

    # Generate blog index pages per language
    print("\n📄 Generating blog index pages...")
    for lang in LANGUAGES:
        cfg    = LANGUAGES[lang]
        prefix = cfg["url_prefix"].lstrip("/")
        index_html = generate_blog_index(lang, all_posts_data)
        out_dir = f"{prefix}/blog" if prefix else "blog"
        os.makedirs(out_dir, exist_ok=True)
        with open(f"{out_dir}/index.html", "w", encoding="utf-8") as f:
            f.write(index_html)
        print(f"  ✅ Blog index: /{out_dir}/")

    # Update sitemap
    print("\n🗺️  Updating sitemap...")
    os.system("python scripts/update_sitemap.py")

    print("\n🚀 Done! Deploy to Netlify to go live.")

if __name__ == "__main__":
    main()
