#!/usr/bin/env python3
"""
Lola Bikes — Sitemap Generator
Scant alle blog/index.html bestanden en maakt een volledige sitemap.xml
"""
import os, glob, datetime

SITE_URL = "https://lolabikes.com"

def main():
    today = datetime.date.today().isoformat()

    urls = []

    # Static pages
    static = [
        ("", 1.0, "weekly"),
        ("/en/", 1.0, "weekly"),
        ("/nl/", 1.0, "weekly"),
        ("/fr/", 1.0, "weekly"),
        ("/de/", 1.0, "weekly"),
        ("/it/", 1.0, "weekly"),
        ("/ru/", 1.0, "weekly"),
        ("/blog/", 0.8, "weekly"),
        ("/en/blog/", 0.8, "weekly"),
        ("/nl/blog/", 0.8, "weekly"),
        ("/fr/blog/", 0.8, "weekly"),
        ("/de/blog/", 0.8, "weekly"),
        ("/it/blog/", 0.8, "weekly"),
        ("/ru/blog/", 0.8, "weekly"),
    ]
    for path, prio, freq in static:
        urls.append((f"{SITE_URL}{path}", prio, freq, today))

    # Blog posts — find all blog/*/index.html
    for html_path in sorted(glob.glob("**/blog/*/index.html", recursive=True)):
        # Convert path to URL
        url_path = "/" + html_path.replace("/index.html", "/").replace("\\", "/")
        if url_path not in [u[0].replace(SITE_URL, "") for u in urls]:
            urls.append((f"{SITE_URL}{url_path}", 0.7, "monthly", today))

    # Build XML
    entries = ""
    for loc, prio, freq, mod in urls:
        entries += f"""  <url>
    <loc>{loc}</loc>
    <lastmod>{mod}</lastmod>
    <changefreq>{freq}</changefreq>
    <priority>{prio}</priority>
  </url>\n"""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{entries}</urlset>"""

    with open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write(xml)

    print(f"  sitemap.xml written — {len(urls)} URLs")

    # Ping Google
    import urllib.request
    try:
        ping_url = f"https://www.google.com/ping?sitemap={SITE_URL}/sitemap.xml"
        urllib.request.urlopen(ping_url, timeout=5)
        print("  Google pinged ✓")
    except:
        print("  (Google ping skipped)")

if __name__ == "__main__":
    main()
