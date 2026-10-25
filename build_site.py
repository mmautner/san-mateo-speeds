"""Build the static site into dist/<base>/.

    python3 build_site.py          # build
    python3 build_site.py --dev    # also write a local stand-in for maxmautner.com's stylesheet

Reads data/ets_2026_segments.json, data/legal_options.json, data/segments_geo.json and
data/city_document_conflicts.csv (all produced by pipeline/run.sh).
"""
import argparse
import csv
import datetime
import hashlib
import html
import json
import re
import shutil
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).parent
SITE = ROOT / "site"
DATA = ROOT / "data"
DIST = ROOT / "dist"
CFG = json.loads((SITE / "config.json").read_text())
BASE = CFG["base"]
OUT = DIST / BASE.strip("/")
e = html.escape

SEGS = {d["segment_no"]: d for d in json.loads((DATA / "ets_2026_segments.json").read_text())}
LEGAL = {d["segment_no"]: d for d in json.loads((DATA / "legal_options.json").read_text())}
GEO = {int(k): v for k, v in json.loads((DATA / "segments_geo.json").read_text()).items()}
CONFLICTS = {int(r["segment_no"]): r for r in csv.DictReader(open(DATA / "city_document_conflicts.csv"))}


def version():
    h = hashlib.sha256()
    for p in sorted([*(SITE / "static").iterdir(), *DATA.glob("*.json")]):
        h.update(p.read_bytes())
    return h.hexdigest()[:10]


VER = version()


def long_date(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d:%B} {d.day}, {d.year}"


def place(name):
    """Survey cross-street names as they read in a sentence."""
    n = name.strip()
    if n.lower() in ("city limit", "mills ave/city limit"):
        return "the city limit" if n.lower() == "city limit" else "Mills Ave (the city limit)"
    return n.replace("Wkwy", "walkway").replace("Ryder Park Crossing", "the Ryder Park crossing")


def segment_label(s):
    return f"{s['street']}, {place(s['from'])} to {place(s['to'])}"


def headline(s):
    return (f"On {s['street']} between {place(s['from'])} and {place(s['to'])}, the limit is {s['existing']}. "
            f"Half of drivers go faster than {s['p50']}; the fastest 15% go faster than {s['p85']}.")


NEEDS = {
    "22358.8": ("by keeping the current limit",
                "The city must confirm the current limit was itself set by an engineering and traffic survey, and a "
                "registered engineer must find that no traffic lanes have been added since."),
    "22358.7": ("with an additional 5 mph reduction",
                "The city must find the limit is still more than is reasonable or safe, and either designate the "
                "street a safety corridor or show that it ranks in the city's worst fifth for people walking or "
                "biking killed or seriously injured and is near a school, park, transit stop or similar place."),
}


def legal_block(s, L):
    lowest_now, basis = L["documented_limit"], L["documented_basis"]
    opts = sorted((p for p in L["possible"] if p["section"] in NEEDS and p["limit"] is not None
                   and p["limit"] < lowest_now), key=lambda p: (p["limit"], p["section"] != "22358.8"))
    lowest = min([lowest_now] + [p["limit"] for p in opts])
    rows = []
    if lowest_now < s["recommended"]:
        rows.append(f"<li><strong>{lowest_now} mph with no further finding</strong> (CVC {e(basis)}). "
                    f"The survey's own numbers allow this.</li>")
    else:
        rows.append(f"<li>{lowest_now} mph using the survey's numbers alone (CVC {e(basis)}).</li>")
    seen = set()
    for p in opts:
        if p["section"] in seen: continue
        seen.add(p["section"])
        how, need = NEEDS[p["section"]]
        rows.append(f"<li><strong>{p['limit']} mph {how}</strong> (CVC {p['section']}). {e(need)}</li>")
    return lowest, "\n".join(rows)


def card(n):
    s, L = SEGS[n], LEGAL[n]
    lowest, rows = legal_block(s, L)
    conflict = CONFLICTS.get(n)
    note = ""
    if conflict:
        note = f'<p class="sp-note">{e(conflict["note"])}</p>'
    pdf = f"{BASE}{CFG['survey_pdf']}#page={s['page']}"
    sample = "not reported on the survey sheet"
    return f"""<article class="sp-card" id="s{n}" tabindex="-1">
  <h3>{e(segment_label(s))}</h3>
  <p class="sp-headline">{e(headline(s))}</p>
  <dl class="sp-dl">
    <div><dt>Current limit</dt><dd>{s['existing']} mph</dd></div>
    <div><dt>Proposed</dt><dd>{s['recommended']} mph</dd></div>
    <div><dt>Lowest legal option</dt><dd>{lowest} mph</dd></div>
  </dl>
  <ul class="sp-options">
{rows}
  </ul>
  {note}
  <p class="sp-meta">Surveyed {e(long_date(s['survey_date']))}. Average daily traffic {s['adt']:,} vehicles. Sample size: {sample}. <a href="{e(pdf)}">Survey sheet (PDF page {s['page']})</a> · <a href="#s{n}" class="sp-share">Link to this street</a></p>
</article>"""


HEADER = """<header role="banner">
  <a href="/" class="site-title">Max Mautner</a>
  <nav role="navigation"><ul>
    <li><a href="/writing/">Essays</a></li>
    <li><a href="/about/">About</a></li>
    <li><a href="/subscribe/" class="nav-button">Subscribe</a></li>
    <li><button class="dark-mode-toggle" id="darkModeToggle" aria-label="Toggle dark mode">
      <svg class="icon-sun" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
      <svg class="icon-moon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
    </button></li>
  </ul></nav>
</header>
<script>(function(){var t=document.getElementById('darkModeToggle'),r=document.documentElement;t.addEventListener('click',function(){var d=r.getAttribute('data-theme')!=='dark';r.setAttribute('data-theme',d?'dark':'light');try{localStorage.setItem('theme',d?'dark':'light')}catch(e){}});})();</script>"""


def head(title, description, path):
    url = f"{CFG['site_url']}{path}"
    return f"""<!DOCTYPE html>
<html lang="en" data-base="{BASE}" data-version="{VER}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script>(function(){{var s=null;try{{s=localStorage.getItem('theme')}}catch(e){{}}var r=document.documentElement;r.setAttribute('data-theme',s||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'));}})();</script>
  <title>{e(title)}</title>
  <meta name="description" content="{e(description)}">
  <link rel="canonical" href="{e(url)}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Max Mautner">
  <meta property="og:title" content="{e(title)}">
  <meta property="og:description" content="{e(description)}">
  <meta property="og:url" content="{e(url)}">
  <link rel="icon" href="/favicon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600;6..72,700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{BASE}static/speeds.css?v={VER}">
  <link rel="stylesheet" href="{CFG['site_css']}">
  <link rel="preconnect" href="https://tiles.openfreemap.org" crossorigin>
  <script defer src="{BASE}static/map.js?v={VER}"></script>
</head>
<body>
<main role="main">
{HEADER}"""


FOOT = "</main>\n</body>\n</html>\n"


def index_page(increases):
    n_all = len(SEGS)
    deferred = [n for n in increases if n not in CONFLICTS or not CONFLICTS[n]["oct5_ordinance_limit"]]
    adopted = [n for n in increases if n in CONFLICTS and CONFLICTS[n]["oct5_ordinance_limit"]]
    title = "Proposed speed limit increases in San Mateo"
    desc = (f"San Mateo's 2026 speed survey proposes higher limits on {len(increases)} street segments. "
            "Measured speeds, current and proposed limits, and the lowest limit state law allows on each.")
    cards = "\n".join(card(n) for n in increases)
    adopted_txt = ""
    if adopted:
        a = SEGS[adopted[0]]
        adopted_txt = (f" One more, {e(segment_label(a))}, appears in the survey as an increase from "
                       f"{a['existing']} to {a['recommended']}, but the city's summary lists its current limit as "
                       f"{CONFLICTS[adopted[0]]['att3_existing']}, and the ordinance the council adopted on "
                       f"<a href=\"{e(CFG['oct5_url'])}\">October 5, 2026</a> sets it at "
                       f"{CONFLICTS[adopted[0]]['oct5_ordinance_limit']}.")
    issue = "mailto:" + CFG["contact_email"] + "?" + urllib.parse.urlencode(
        {"subject": "Possible error: San Mateo speeds page"}, quote_via=urllib.parse.quote)
    return head(title, desc, BASE) + f"""
<article class="sp">
  <span class="sp-eyebrow">San Mateo speed survey, 2026</span>
  <h1>{len(increases)} streets where the city's survey proposes a higher speed limit</h1>
  <p class="sp-lede">This spring the city measured how fast drivers go on {n_all} street segments. On {len(increases)} of them, the fastest 15% of drivers went fast enough that the survey proposes raising the limit. State law gives the city other choices. Below are the measured speeds on each street and the lowest limit the law allows.</p>

  <div class="sp-status">
    <p><strong>Status.</strong> On September 22, 2026, the City Council set aside the {len(deferred)} proposed increases (<a href="{e(CFG['item16_url'])}">Item 16</a>) and asked staff to bring them back at a future study session. No date has been set.{adopted_txt}</p>
  </div>

  <h2>How a speed survey sets the limit</h2>
  <p>On larger streets, California ties the speed limit to the speed that the fastest 15% of drivers exceed, called the 85th-percentile speed. The limit is that speed rounded to the nearest 5 mph, minus reductions the law allows (Vehicle Code 22358.6). Drivers going slower than that speed don't change it. When the fastest 15% speed up, the next survey can raise the limit again. A survey is valid for 7 years (Vehicle Code 40802).</p>
  <p>Since 2022, state law (AB 43) has let cities round down, keep a current limit, or cut 5 mph more on streets with crash histories or many people walking and biking. Each street below lists the options that apply and what each one requires.</p>
  <p>For a person walking, the average risk of death is about 10% if struck at 23 mph and about 25% if struck at 32 mph. These are impact speeds, the speed at the moment of the crash (<a href="{e(CFG['tefft_url'])}">AAA Foundation for Traffic Safety, Tefft 2011</a>).</p>

  <h2>Where they are</h2>
  <div id="sp-map" class="sp-map" role="region" aria-label="Map of the {len(increases)} street segments with proposed increases. The same streets are listed below."></div>
  <noscript><p class="sp-meta">The map needs JavaScript. Every street is listed below.</p></noscript>

  <h2>The {len(increases)} streets</h2>
  <p class="sp-meta">Ordered by how far the fastest 15% exceed the current limit. Speeds are miles per hour.</p>
  <div class="sp-list">
{cards}
  </div>

  <h2 id="about">About these numbers</h2>
  <ul class="sp-about">
    <li><strong>Speeds</strong> come from the city's 2026 Engineering and Traffic Survey summary sheets (DKS Associates, signed August 2026), obtained through a public records request. <a href="{BASE}{e(CFG['survey_pdf'])}">The full survey (PDF, 20 MB)</a>. Counts were taken March 10 to July 17, 2026. The sheets do not report how many vehicles were measured.</li>
    <li><strong>Current and proposed limits</strong> come from the survey sheets. Where they differ from the city's summary for the Sept. 22 meeting (<a href="{e(CFG['att3_url'])}">Attachment 3</a>), the difference is noted on that street.</li>
    <li><strong>Lowest limit the law allows</strong> applies California Vehicle Code sections 22358.6, 22358.7 and 22358.8, and the California Manual on Uniform Traffic Control Devices (2026), section 2B.21, to each sheet. "No further finding" means the survey's own numbers already allow it. The other options depend on facts the survey doesn't record, and each lists what is needed. Business district limits (section 22358.9) were not assessed. Limits below 20 mph are not shown. This is a reading of the statutes, not legal advice.</li>
    <li><strong>Map lines</strong> are drawn on OpenStreetMap streets between the survey's cross streets. Map data © OpenStreetMap contributors; tiles by OpenFreeMap.</li>
  </ul>
  <p class="sp-meta">Updated {e(long_date(CFG['updated']))}. Made by <a href="/about/">Max Mautner</a>. <a href="{e(issue)}">Report an error</a>.</p>
</article>
<script type="application/json" id="sp-data">{json.dumps(geojson(increases), separators=(",", ":"))}</script>
""" + FOOT


def geojson(ns):
    feats = []
    for n in ns:
        g = GEO.get(n)
        if not g or "coords" not in g: continue
        s = SEGS[n]
        feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": g["coords"]},
                      "properties": {"id": f"s{n}", "label": segment_label(s),
                                     "text": f"{s['existing']} → {s['recommended']} proposed; fastest 15% over {s['p85']}"}})
    return {"type": "FeatureCollection", "features": feats}


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", action="store_true")
    a = ap.parse_args()
    increases = sorted((n for n, s in SEGS.items() if s["recommended"] > s["existing"]),
                       key=lambda n: (-(SEGS[n]["p85"] - SEGS[n]["existing"]), SEGS[n]["street"], n))
    missing = [n for n in increases if "coords" not in GEO.get(n, {})]
    if missing:
        print("no geometry for", missing, file=sys.stderr)
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SITE / "static", OUT / "static")
    (OUT / "sources").mkdir(parents=True)
    shutil.copy(DATA / "sources/ets_2026_summary_sheets_redacted.pdf", OUT / CFG["survey_pdf"])
    write(OUT / "index.html", index_page(increases))
    if a.dev:
        blog = ROOT.parent / "maxmautner" / "_site" / "index.html"
        m = re.search(r"<style>(.*?)</style>", blog.read_text(), re.S) if blog.exists() else None
        if m:
            write(DIST / CFG["site_css"].lstrip("/"), m.group(1))
        else:
            print("no built blog found for --dev stylesheet", file=sys.stderr)
    print(f"built {len(increases)} segments into {OUT} (version {VER})", file=sys.stderr)


if __name__ == "__main__":
    main()
