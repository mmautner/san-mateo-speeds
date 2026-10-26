"""Build the static site into dist/<base>/.

    python3 build_site.py          # build
    python3 build_site.py --dev    # also write a local stand-in for maxmautner.com's stylesheet

Reads data/ets_2026_segments.json, data/legal_options.json, data/segments_geo.json,
data/city_document_conflicts.csv (all produced by pipeline/run.sh) and site/council.json.

Pages: index (map + sortable list), one page per surveyed segment, methodology.
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
COUNCIL = json.loads((SITE / "council.json").read_text())
BASE = CFG["base"]
OUT = DIST / BASE.strip("/")
e = html.escape

SEGS = {d["segment_no"]: d for d in json.loads((DATA / "ets_2026_segments.json").read_text())}
LEGAL = {d["segment_no"]: d for d in json.loads((DATA / "legal_options.json").read_text())}
GEO = {int(k): v for k, v in json.loads((DATA / "segments_geo.json").read_text()).items()}
CONFLICTS = {int(r["segment_no"]): r for r in csv.DictReader(open(DATA / "city_document_conflicts.csv"))}
DISTRICTS = json.loads((DATA / "sources/geo/council_districts.geojson").read_text())["features"]

FHWA_PSC = "https://highways.dot.gov/safety/proven-safety-countermeasures"
FHWA_M4 = "https://highways.dot.gov/safety/speed-management/traffic-calming-eprimer/module-4-effects-traffic-calming-measures-motor"
NTMP = "https://www.cityofsanmateo.org/DocumentCenter/View/1211"
NTMP_PAGE = "https://www.cityofsanmateo.org/3329/City-Staff-Evaluation-Process"
CALMING_FORM = "https://cityofsanmateo.org/forms.aspx?fid=111"
SERVICE_REQ = "https://www.cityofsanmateo.org/4940"
LRSP = "https://www.cityofsanmateo.org/Safetyplan"
MEMO = f"{CFG['repo_url']}/blob/main/docs/legal-memo.md"

BINS = [  # how far the 85th-percentile speed is over the posted limit
    (lambda x: x <= 0, "At or under the limit"),
    (lambda x: 1 <= x <= 4, "1 to 4 mph over"),
    (lambda x: 5 <= x <= 7, "5 to 7 mph over"),
    (lambda x: x >= 8, "More than 7 mph over"),
]


def bin_of(s):
    over = s["p85"] - s["existing"]
    return next(i for i, (f, _) in enumerate(BINS) if f(over))


def version():
    h = hashlib.sha256()
    for p in sorted([*(SITE / "static").iterdir(), *DATA.glob("*.json"), SITE / "council.json", SITE / "config.json"]):
        h.update(p.read_bytes())
    return h.hexdigest()[:10]


VER = version()


def long_date(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d:%B} {d.day}, {d.year}"


def place(name):
    """Survey cross-street names as they read in a sentence."""
    n = name.strip()
    low = n.lower()
    if low == "city limit": return "the city limit"
    if low == "mills ave/city limit": return "Mills Ave (the city limit)"
    if low == "92 off-ramp": return "the SR-92 ramps"
    if low == "sf bay trail": return "the Bay Trail"
    return n.replace("Wkwy", "walkway").replace("Ryder Park Crossing", "the Ryder Park crossing")


def segment_label(s):
    return f"{s['street']}, {place(s['from'])} to {place(s['to'])}"


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", f"{s['street']} {s['from']} to {s['to']}".lower()).strip("-")


SLUGS = {}
for _n, _s in sorted(SEGS.items()):
    _k = slug(_s)
    SLUGS[_n] = _k if _k not in SLUGS.values() else f"{_k}-{_n}"


def url(n):
    return f"{BASE}{SLUGS[n]}/"


def street_type(s):
    m = re.search(r"classified as an? (minor arterial|major collector)", s.get("description") or "", re.I)
    return m.group(1).lower() if m else "street"


def headline(s):
    return (f"On {s['street']} between {place(s['from'])} and {place(s['to'])}, the limit is {s['existing']}. "
            f"Half of drivers go faster than {s['p50']}; the fastest 15% go faster than {s['p85']}.")


def proposal(s):
    if s["recommended"] > s["existing"]: return f"raising the limit to {s['recommended']} mph"
    if s["recommended"] < s["existing"]: return f"lowering the limit to {s['recommended']} mph"
    return f"keeping the limit at {s['recommended']} mph"


def proposal_kind(s):
    return "increase" if s["recommended"] > s["existing"] else ("decrease" if s["recommended"] < s["existing"] else "no_change")


# ------------------------------------------------------------------ legal options
NEEDS = {
    "22358.8": ("by keeping the current limit",
                "The city must confirm the current limit was itself set by an engineering and traffic survey, and a "
                "registered engineer must find that no traffic lanes have been added since."),
    "22358.7": ("with an additional 5 mph reduction",
                "The city must find the limit is still more than is reasonable or safe, and the street must qualify "
                "one of two ways. The law allows it on a designated safety corridor; the state's traffic manual "
                "defines these as the streets with the most deaths and serious injuries, and the law caps them at a "
                "fifth of city streets. The law also allows it next to places that draw many people walking or "
                "biking, such as a school, park or transit stop; the manual adds that the street must rank in the "
                "city's worst fifth for people walking or biking killed or seriously injured over 3 to 5 years."),
}


def legal(n):
    """(lowest, how, section, list items) for segment n. 22358.9 business districts are not assessed."""
    s, L = SEGS[n], LEGAL[n]
    now, basis = L["documented_limit"], L["documented_basis"]
    opts, seen = [], set()
    for p in sorted((p for p in L["possible"] if p["section"] in NEEDS and p["limit"] is not None and p["limit"] < now),
                    key=lambda p: (p["limit"], p["section"] != "22358.8")):
        if p["section"] not in seen:
            seen.add(p["section"]); opts.append(p)
    items = []
    if now < s["recommended"]:
        items.append(f"<li><strong>{now} mph with no further finding</strong> (CVC {e(basis)}). The survey's own numbers allow this.</li>")
    else:
        items.append(f"<li>{now} mph using the survey's numbers alone (CVC {e(basis)}).</li>")
    for p in opts:
        how, need = NEEDS[p["section"]]
        items.append(f"<li><strong>{p['limit']} mph {how}</strong> (CVC {p['section']}). {e(need)}</li>")
    if opts:
        low = opts[0]
        return low["limit"], NEEDS[low["section"]][0], low["section"], items
    return now, "using the survey's own numbers", basis, items


# ------------------------------------------------------------------ council districts
def _polys(f):
    g = f["geometry"]
    return [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]


def _inside(pt, poly):
    x, y = pt; c = False
    for ring in poly:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: c = not c
    return c


def districts(n):
    coords = GEO.get(n, {}).get("coords") or []
    found = []
    for pt in coords:
        for f in DISTRICTS:
            d = str(f["properties"]["DISTRICT"])
            if d not in found and any(_inside(pt, p) for p in _polys(f)): found.append(d)
    if not found and coords:  # line runs along the city edge: use the nearest district boundary point
        mid = coords[len(coords) // 2]
        found = [min(((abs(mid[0] - x) + abs(mid[1] - y), str(f["properties"]["DISTRICT"]))
                      for f in DISTRICTS for poly in _polys(f) for ring in poly for x, y in ring))[1]]
    return sorted(found)


# ------------------------------------------------------------------ page chrome
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


def analytics():
    """The same Google Analytics tag as maxmautner.com (_includes/analytics.html in the blog)."""
    key = CFG.get("google_analytics_key")
    if not key: return ""
    return f"""<script async src="https://www.googletagmanager.com/gtag/js?id={key}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{key}');
  </script>"""


def head(title, description, path, scripts=("map.js",), og="index", segment=""):
    page_url = f"{CFG['site_url']}{path}"
    scripts = ("analytics.js", *scripts)
    img = f"{CFG['site_url']}{BASE}og/{og}.png"  # rendered by site/og/make_og.py
    js = "\n".join(f'  <script defer src="{BASE}static/{s}?v={VER}"></script>' for s in scripts)
    return f"""<!DOCTYPE html>
<html lang="en" data-base="{BASE}" data-version="{VER}" data-segment="{e(segment)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script>(function(){{var s=null;try{{s=localStorage.getItem('theme')}}catch(e){{}}var r=document.documentElement;r.setAttribute('data-theme',s||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'));}})();</script>
  <title>{e(title)}</title>
  <meta name="description" content="{e(description)}">
  <link rel="canonical" href="{e(page_url)}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Max Mautner">
  <meta property="og:title" content="{e(title)}">
  <meta property="og:description" content="{e(description)}">
  <meta property="og:url" content="{e(page_url)}">
  <meta property="og:image" content="{e(img)}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="{e(description)}">
  <meta name="twitter:card" content="summary_large_image">
  {analytics()}
  <link rel="icon" href="/favicon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600;6..72,700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{BASE}static/speeds.css?v={VER}">
  <link rel="stylesheet" href="{CFG['site_css']}">
  <link rel="preconnect" href="https://tiles.openfreemap.org" crossorigin>
{js}
</head>
<body>
<main role="main">
{HEADER}"""


FOOT = "</main>\n</body>\n</html>\n"


def small_print():
    issue = "mailto:" + CFG["contact_email"] + "?" + urllib.parse.urlencode(
        {"subject": "Possible error: San Mateo speeds page"}, quote_via=urllib.parse.quote)
    return f"""<footer class="sp-foot">
  <p>Speeds and limits: City of San Mateo 2026 Engineering and Traffic Survey (DKS Associates), obtained through a public records request. <a href="{BASE}methodology/">How this was made</a>.</p>
  <p>Made by <a href="/about/">Max Mautner</a>. <a href="{e(CFG['repo_url'])}">The data and code are public</a>, including the <a href="{e(MEMO)}">legal memo</a>, so anyone can check how each number was reached. <a href="{e(issue)}">Report an error</a>.</p>
  <p>Updated {e(long_date(CFG['updated']))}. A reading of state law, not legal advice.</p>
</footer>"""


PED_RISK = (f'<p class="sp-risk">For a person walking, the average risk of death is about 10% if struck at 23 mph and '
            f'about 25% if struck at 32 mph. These are impact speeds, the speed at the moment of the crash '
            f'(<a href="{e(CFG["tefft_url"])}">AAA Foundation for Traffic Safety, Tefft 2011</a>).</p>')


def legend():
    return ('<ul class="sp-legend" aria-label="Map colors: how far the fastest 15% go over the limit">' + "".join(
        f'<li><span class="sp-swatch sp-b{i}" aria-hidden="true"></span>{e(label)} ({n})</li>'
        for i, ((_, label), n) in enumerate(zip(BINS, bin_counts()))) + "</ul>")


def bin_counts():
    return [sum(1 for s in SEGS.values() if bin_of(s) == i) for i in range(len(BINS))]


def geojson(ns):
    feats = []
    for n in ns:
        g = GEO.get(n)
        if not g or "coords" not in g: continue
        s = SEGS[n]
        feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": g["coords"]},
                      "properties": {"url": url(n), "bin": bin_of(s), "label": segment_label(s),
                                     "text": f"Limit {s['existing']}; fastest 15% go faster than {s['p85']}"}})
    return {"type": "FeatureCollection", "features": feats}


def data_tag(ns, mode):
    return (f'<script type="application/json" id="sp-data" data-mode="{mode}">'
            f'{json.dumps(geojson(ns), separators=(",", ":"))}</script>')


# ------------------------------------------------------------------ street-type option cards
def fhwa(sheet):
    return f'<a href="{FHWA_PSC}">FHWA Proven Safety Countermeasures, {sheet}</a>'


def m4(section):
    return f'<a href="{FHWA_M4}">FHWA Traffic Calming ePrimer, Module 4, {section}</a>'


POLICY_EXCLUDES = (f'The city\'s <a href="{NTMP}">2006 traffic calming policy</a> does not allow speed humps, traffic '
                   f'circles or other physical calming devices on collectors or arterials, so changes on these streets '
                   f'come through city street projects. The city\'s <a href="{LRSP}">Local Roadway Safety Plan</a> '
                   f'lists its priorities.')

ARTERIAL = [
    ("Pedestrian refuge island", f"up to 56% fewer pedestrian crashes ({fhwa('FHWA-SA-21-044')}). FHWA suggests them on multilane streets with more than 9,000 vehicles a day or speeds of 35 mph or more."),
    ("Flashing beacon at a crosswalk (RRFB)", f"up to 47% fewer pedestrian crashes at uncontrolled marked crosswalks ({fhwa('FHWA-SA-21-053')})."),
    ("Leading pedestrian interval", f"a few seconds' head start on the walk signal: 13% fewer pedestrian-vehicle crashes at intersections ({fhwa('FHWA-SA-21-032')})."),
    ("High-visibility crosswalk and lighting", f"up to 40% fewer pedestrian injury crashes for the crosswalk markings, and up to 42% fewer pedestrian crashes for intersection lighting ({fhwa('FHWA-SA-21-049')})."),
    ("Four lanes to three (road diet)", f"19% to 47% fewer crashes overall, usually on streets carrying 25,000 vehicles a day or fewer ({fhwa('FHWA-SA-21-046')})."),
]
COLLECTOR = [
    ("Bike lanes", f"up to 30% fewer crashes overall on urban two-lane collectors, and up to 49% on four-lane ones ({fhwa('FHWA-SA-21-051')})."),
    ("High-visibility crosswalk", f"up to 40% fewer pedestrian injury crashes; advance yield markings, up to 25% fewer pedestrian crashes ({fhwa('FHWA-SA-21-049')})."),
    ("Flashing beacon at a crosswalk (RRFB)", f"up to 47% fewer pedestrian crashes at uncontrolled marked crosswalks ({fhwa('FHWA-SA-21-053')})."),
    ("Chicane (alternating curb extensions)", f"on two-lane, two-way streets, 85th-percentile speeds averaged 31 to 33 mph after installation ({m4('Table 4.1')})."),
]
NEIGHBORHOOD = [
    ("Speed humps", f"after installation, the speed the fastest 15% exceed was most often 25 to 27 mph (218 humps). Drivers going 10 mph or more over the limit fell from 14% of traffic to 1% (26 humps) ({m4('section 4.1')})."),
    ("Speed tables and raised crosswalks", f"most often 30 to 32 mph afterward (90 tables) ({m4('section 4.2')})."),
    ("Traffic circles", f"most often 27 to 28 mph afterward (47 circles) ({m4('section 4.4')})."),
]


def options_list(items):
    return '<ul class="sp-opts">' + "".join(f"<li><strong>{e(t)}:</strong> {body}</li>" for t, body in items) + "</ul>"


def neighborhood_card():
    return f"""<section class="sp-box" aria-labelledby="nb-h">
  <h3 id="nb-h">Options for neighborhood streets</h3>
  {options_list(NEIGHBORHOOD)}
  <p>Under the city's <a href="{NTMP}">2006 traffic calming policy</a>, still its guiding document (<a href="{NTMP_PAGE}">city page</a>), physical devices like these need:</p>
  <ul class="sp-opts">
    <li>a measured 85th-percentile speed <strong>more than 7 mph over the limit</strong> (the city measures with tube counters);</li>
    <li>support from a majority of residents who answer the city's survey;</li>
    <li>a street that isn't a collector, arterial, emergency route, bus route or truck route.</li>
  </ul>
  <p>Devices that divert traffic, such as turn restrictions or diverters, also need more than 1,000 vehicles a day with at least a quarter cutting through. To start, use the city's <a href="{CALMING_FORM}">traffic calming request form</a> or <a href="{SERVICE_REQ}">My San Mateo</a>.</p>
</section>"""


def type_card(n):
    s = SEGS[n]
    t = street_type(s)
    over = s["p85"] - s["existing"]
    test = "passes" if over > 7 else "does not pass"
    items = ARTERIAL if t == "minor arterial" else COLLECTOR
    name = "arterials" if t == "minor arterial" else "collectors"
    return f"""<section class="sp-box" aria-labelledby="type-h">
  <h2 id="type-h">Options for {name} like this one</h2>
  <p>The survey classifies this segment as a {e(t)}. Typical effects, from federal research:</p>
  {options_list(items)}
  <p>{POLICY_EXCLUDES} For reference, this segment {test} the policy's speed test: the fastest 15% go {abs(over)} mph {"over" if over >= 0 else "under"} the limit, and the test is more than 7. The survey doesn't measure cut-through traffic, so the policy's volume test can't be checked here.</p>
</section>"""


# ------------------------------------------------------------------ ask the city
def ask(n):
    s = SEGS[n]
    ds = districts(n)
    members = [COUNCIL["members"][d] for d in ds]
    pw = COUNCIL["public_works"]
    to = [m["email"] for m in members] + [pw["email"]]
    names = [m["salutation"] for m in members] + [pw["salutation"]]
    greet = ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + names[-1]
    low, how, sec, _ = legal(n)
    cond = {"22358.8": ", by keeping the current limit, if that limit was set by an earlier survey and no lanes have been added",
            "22358.7": ", with an additional 5 mph reduction, if it qualifies as a safety corridor or as a street near places that draw many people walking or biking"
            }.get(sec, "")
    body = (f"Dear {greet},\n\n"
            f"The city's 2026 speed survey measured traffic on {s['street']} between {place(s['from'])} and {place(s['to'])} "
            f"on {long_date(s['survey_date'])}. The limit there is {s['existing']} mph. Half of drivers went faster than "
            f"{s['p50']} mph, and the fastest 15% went faster than {s['p85']} mph. The survey proposes {proposal(s)}.\n\n"
            f"State law would allow a limit as low as {low} mph on this street{cond} (Vehicle Code {sec}).\n\n"
            f"\n\n"
            f"Will the city set the lowest limit state law allows on this street?")
    subject = f"Speed limit on {s['street']} ({place(s['from'])} to {place(s['to'])})"
    href = "mailto:" + ",".join(to) + "?" + urllib.parse.urlencode({"subject": subject, "body": body}, quote_via=urllib.parse.quote)
    people = [f"{m['salutation']} (District {d})" for m, d in zip(members, ds)] + [f"{pw['name']}, {pw['title']}"]
    who = ", ".join(people[:-1]) + " and " + people[-1] if len(people) > 2 else " and ".join(people)
    preview = e(body).replace("\n\n\n\n", '\n\n<span class="sp-blank">Add a sentence of your own here.</span>\n')
    return f"""<section class="sp-box sp-ask" aria-labelledby="ask-h">
  <h2 id="ask-h">Ask the city</h2>
  <p>This opens an email to {e(who)}, with this street's numbers filled in. There's a blank line for a sentence of your own.</p>
  <p class="sp-meta">To: {e(", ".join(to))}<br>Subject: {e(subject)}</p>
  <pre class="sp-email">{preview}</pre>
  <p class="sp-actions"><a class="sp-btn" href="{e(href)}" data-track="ask_email_clicked" data-track-districts="{e(",".join(ds))}" data-track-proposal="{e(proposal_kind(s))}">Write the email</a> <button type="button" class="sp-btn sp-btn-2" data-copy="sp-email-text" data-copy-event="email_text_copied">Copy the text</button> <span class="sp-copied" role="status"></span></p>
  <textarea id="sp-email-text" hidden>{e(body)}</textarea>
  <p class="sp-meta">Council members as of {e(long_date(COUNCIL['checked']))}, by the districts this segment crosses. {e(pw['name'])} is the staff contact named on the speed limit update; the city lists no general Public Works email.</p>
</section>"""


# ------------------------------------------------------------------ pages
def status_html():
    deferred = sum(1 for n, s in SEGS.items() if s["recommended"] > s["existing"]
                   and not (n in CONFLICTS and CONFLICTS[n]["oct5_ordinance_limit"]))
    return (f'On September 22, 2026, the City Council set aside {deferred} proposed increases (<a href="{e(CFG["item16_url"])}">Item 16</a>) '
            f'and asked staff to bring them back at a future study session. No date has been set. On '
            f'<a href="{e(CFG["oct5_url"])}">October 5</a> it adopted the limits that don\'t increase.')


def segment_page(n):
    s = SEGS[n]
    low, how, sec, items = legal(n)
    conflict = CONFLICTS.get(n)
    note = f'<p class="sp-note">{e(conflict["note"])}</p>' if conflict else ""
    pdf = f"{BASE}{CFG['survey_pdf']}#page={s['page']}"
    path = url(n)
    title = f"Speeds on {segment_label(s)}, San Mateo"
    has_map = "coords" in GEO.get(n, {})
    mapdiv = (f'<div id="sp-map" class="sp-map sp-map-small" role="img" aria-label="Map of {e(segment_label(s))}"></div>'
              if has_map else '<p class="sp-meta">This segment could not be drawn on the map.</p>')
    over = s["p85"] - s["existing"]
    return head(title, headline(s), path, scripts=("map.js", "page.js"), og=SLUGS[n], segment=SLUGS[n]) + f"""
<article class="sp sp-seg">
  <span class="sp-eyebrow"><a href="{BASE}">San Mateo speed survey, 2026</a> · <a href="{BASE}#list">All {len(SEGS)} streets</a></span>
  <h1>{e(segment_label(s))}</h1>
  <p class="sp-headline">{e(headline(s))}</p>
  <dl class="sp-dl">
    <div><dt>Current limit</dt><dd>{s['existing']} mph</dd></div>
    <div><dt>Proposed</dt><dd>{s['recommended']} mph</dd></div>
    <div><dt>Lowest legal option</dt><dd>{low} mph</dd></div>
  </dl>
  <h2>What state law allows here</h2>
  <ul class="sp-options">
{chr(10).join(items)}
  </ul>
  {note}
  <p class="sp-meta">Surveyed {e(long_date(s['survey_date']))}. Sample size: not reported on the survey sheet. Average daily traffic {s['adt']:,} vehicles. The fastest 15% go {abs(over)} mph {"over" if over >= 0 else "under"} the limit. <a href="{e(pdf)}" data-track="survey_pdf_opened" data-track-pdf-page="{s['page']}">Survey sheet (PDF page {s['page']})</a>.</p>
  {mapdiv}
  {PED_RISK}
  {type_card(n)}
  {ask(n)}
  <section class="sp-box sp-share" aria-labelledby="share-h">
    <h2 id="share-h">Share this street</h2>
    <p class="sp-actions"><input type="text" readonly value="{e(CFG['site_url'] + path)}" id="sp-url" aria-label="Link to this page"> <button type="button" class="sp-btn sp-btn-2" data-copy="sp-url" data-copy-event="link_copied">Copy link</button> <span class="sp-copied" role="status"></span></p>
  </section>
  {small_print()}
</article>
{data_tag([n], "single")}
""" + FOOT


def table_rows():
    rows = []
    for n, s in sorted(SEGS.items(), key=lambda kv: (-(kv[1]["p85"] - kv[1]["existing"]), kv[1]["street"])):
        low = legal(n)[0]
        over = s["p85"] - s["existing"]
        inc = s["recommended"] > s["existing"]
        rows.append(f"""<tr data-inc="{int(inc)}" id="s{n}">
  <th scope="row" data-v="{e(s['street'] + ' ' + s['from'])}"><a href="{url(n)}">{e(s['street'])}</a><span>{e(place(s['from']))} to {e(place(s['to']))}</span></th>
  <td data-v="{s['existing']}">{s['existing']}</td>
  <td data-v="{s['p50']}">{s['p50']}</td>
  <td data-v="{s['p85']}">{s['p85']}</td>
  <td data-v="{over}"><span class="sp-chip sp-b{bin_of(s)}" aria-hidden="true"></span>{over:+d}</td>
  <td data-v="{s['recommended']}">{s['recommended']}{' <span class="sp-up">increase</span>' if inc else ''}</td>
  <td data-v="{low}">{low}</td>
</tr>""")
    return "\n".join(rows)


def index_page():
    inc = [n for n, s in SEGS.items() if s["recommended"] > s["existing"]]
    n_all = len(SEGS)
    counts = bin_counts()
    p50_over = sum(1 for s in SEGS.values() if s["p50"] > s["existing"])
    title = "How fast drivers go on San Mateo's surveyed streets"
    desc = (f"Measured speeds on all {n_all} street segments in San Mateo's 2026 speed survey, the limits the city proposes, "
            "and the lowest limits state law allows.")
    return head(title, desc, BASE, scripts=("map.js", "table.js")) + f"""
<article class="sp">
  <span class="sp-eyebrow">San Mateo speed survey, 2026</span>
  <h1>How fast drivers go on San Mateo's surveyed streets</h1>
  <p class="sp-lede">This spring the city measured traffic on {n_all} segments of its larger streets. On {counts[2] + counts[3]} of them, the fastest 15% of drivers went at least 5 mph over the limit. On {len(inc)}, they went fast enough that the survey proposes raising the limit for everyone.</p>

  <div class="sp-status"><p><strong>Status.</strong> {status_html()}</p></div>

  <h2>How a speed survey sets the limit</h2>
  <p>On larger streets, California ties the speed limit to the speed the fastest 15% of drivers exceed, called the 85th-percentile speed. The limit is that speed rounded to the nearest 5 mph, minus reductions the law allows (Vehicle Code 22358.6). Drivers going slower than that speed don't change it. When the fastest 15% speed up, the next survey can raise the limit again. A survey is valid for 7 years (Vehicle Code 40802).</p>
  <p>Since 2022, state law (AB 43) has let cities round down, keep a current limit, or cut 5 mph more on streets with crash histories or many people walking and biking. Each street's page lists the options that apply and what each requires.</p>
  {PED_RISK}

  <h2>The map</h2>
  <p>Each line is a surveyed segment, colored by how far the fastest 15% go over the posted limit. On {p50_over} of the {n_all}, half of drivers go faster than the limit. Tap a line to open that street.</p>
  {legend()}
  <div id="sp-map" class="sp-map" role="region" aria-label="Map of all {n_all} surveyed segments. The same streets are listed in the table below."></div>
  <noscript><p class="sp-meta">The map needs JavaScript. Every street is in the table below.</p></noscript>

  <h2 id="list">All {n_all} surveyed segments</h2>
  <p class="sp-meta">Speeds in mph. "Half go faster than" is the median speed; "Fastest 15% go faster than" is the 85th percentile. Tap a column heading to sort.</p>
  <div class="sp-filter" role="group" aria-label="Which segments to show">
    <button type="button" class="sp-btn sp-btn-2" aria-pressed="true" data-filter="all">All {n_all}</button>
    <button type="button" class="sp-btn sp-btn-2" aria-pressed="false" data-filter="inc">Proposed increases ({len(inc)})</button>
  </div>
  <div class="sp-table-wrap" tabindex="0" role="region" aria-label="Table of surveyed segments, scrolls sideways">
  <table class="sp-table" id="sp-table">
    <thead><tr>
      <th scope="col" aria-sort="none"><button type="button" data-sort="text">Street</button></th>
      <th scope="col" aria-sort="none"><button type="button" data-sort="num">Limit</button></th>
      <th scope="col" aria-sort="none"><button type="button" data-sort="num">Half go faster than</button></th>
      <th scope="col" aria-sort="none"><button type="button" data-sort="num">Fastest 15% go faster than</button></th>
      <th scope="col" aria-sort="descending"><button type="button" data-sort="num">Over the limit</button></th>
      <th scope="col" aria-sort="none"><button type="button" data-sort="num">Proposed</button></th>
      <th scope="col" aria-sort="none"><button type="button" data-sort="num">Lowest legal option</button></th>
    </tr></thead>
    <tbody>
{table_rows()}
    </tbody>
  </table>
  </div>
  <p class="sp-meta">"Lowest legal option" may depend on a city finding or a records check; each street's page says what's needed. Where the survey sheet and the city's summary disagree, the street's page notes it.</p>

  <h2 id="not-surveyed">Is your street missing?</h2>
  <p>Most San Mateo streets weren't surveyed. On most residential streets, state law sets a 25 mph limit without a survey (Vehicle Code 22352), so the city surveys only larger streets where it posts other limits. All {n_all} segments here are arterials or collectors. If your street isn't listed, it wasn't measured in this survey.</p>
  {neighborhood_card()}

  {small_print()}
</article>
{data_tag(sorted(SEGS), "all")}
""" + FOOT


def methodology_page():
    dates = sorted(s["survey_date"] for s in SEGS.values())
    approx = [n for n, g in GEO.items() if g.get("status") in ("approx", "check")]
    title = "How the San Mateo speeds pages were made"
    return head(title, "Sources and methods for the San Mateo speed survey pages.", f"{BASE}methodology/", scripts=()) + f"""
<article class="sp">
  <span class="sp-eyebrow"><a href="{BASE}">San Mateo speed survey, 2026</a></span>
  <h1>How this was made</h1>

  <h2>The survey</h2>
  <ul class="sp-about">
    <li><strong>Source.</strong> City of San Mateo Engineering and Traffic Survey summary sheets, prepared by DKS Associates and signed by a registered engineer in August 2026, obtained through a public records request: <a href="{BASE}{e(CFG['survey_pdf'])}" data-track="survey_pdf_opened" data-track-pdf-page="all">the full PDF (20 MB)</a>. One sheet per segment, {len(SEGS)} segments.</li>
    <li><strong>Dates.</strong> Speeds were measured {e(long_date(dates[0]))} to {e(long_date(dates[-1]))}. Each street's page gives its survey date.</li>
    <li><strong>What the sheets report.</strong> Posted and recommended limits, the 50th- and 85th-percentile speeds, the 10 mph pace, average daily traffic, and 2021–2025 collisions. They do not report how many vehicles were measured, so no sample sizes are shown.</li>
    <li><strong>How it was read.</strong> Most pages are scans, so the numbers were read by optical character recognition and then checked. On every sheet, the printed collision rate is reproduced from the collision count, daily traffic and segment length. The 85th-percentile speed and recommended limit match the sheet's written recommendation wherever it was legible, and the rest were checked by eye. A short list of hand corrections is in the code.</li>
    <li><strong>Where the city's documents differ.</strong> On four segments, the survey sheet and the city's summary for the September 22, 2026 council meeting (<a href="{e(CFG['att3_url'])}">Attachment 3</a>) disagree about the current or proposed limit. These pages use the survey sheet and note the difference on each.</li>
  </ul>

  <h2>Lowest legal option</h2>
  <ul class="sp-about">
    <li>Each segment's options apply California Vehicle Code sections 22358.6 (rounding and documented reductions), 22358.7 (an extra 5 mph on safety corridors or near places that draw people walking and biking) and 22358.8 (keeping the current limit), with the California Manual on Uniform Traffic Control Devices (2026), section 2B.21.</li>
    <li>"No further finding" means the survey's own 85th-percentile speed already allows that limit. The other options depend on facts the survey doesn't record, and each lists what is needed. Business district limits (section 22358.9) were not assessed. Limits below 20 mph are not shown.</li>
    <li>The reasoning, the statute text and every source are in the <a href="{e(MEMO)}">legal memo</a>. This is a reading of the statutes, not legal advice.</li>
  </ul>

  <h2>Street options</h2>
  <ul class="sp-about">
    <li>Typical effects come from the Federal Highway Administration's <a href="{FHWA_PSC}">Proven Safety Countermeasures</a> fact sheets (2021) and the <a href="{FHWA_M4}">Traffic Calming ePrimer, Module 4</a>. Copies are in the repository.</li>
    <li>Street types are the survey's own classification (minor arterial or major collector). The city's traffic calming policy goes by the General Plan's classification, which was not checked segment by segment.</li>
    <li>The pedestrian risk figures are from Tefft, B.C. (2011), <a href="{e(CFG['tefft_url'])}"><em>Impact Speed and a Pedestrian's Risk of Severe Injury or Death</em></a>, AAA Foundation for Traffic Safety.</li>
  </ul>

  <h2>Map and emails</h2>
  <ul class="sp-about">
    <li>Segments are drawn on OpenStreetMap streets between the survey's cross streets, choosing the path whose length best matches the sheet. {len(approx)} segments end at a ramp, walkway, trail or the city limit and are placed partly by length. Map data © OpenStreetMap contributors (ODbL); tiles by OpenFreeMap.</li>
    <li>"Ask the city" emails go to the council members whose districts the segment crosses (district boundaries from the city) and to the staff contact named on the speed limit update. Council members as of {e(long_date(COUNCIL['checked']))}.</li>
  </ul>
  {small_print()}
</article>
""" + FOOT


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", action="store_true")
    a = ap.parse_args()
    missing = [n for n in SEGS if "coords" not in GEO.get(n, {})]
    if missing:
        print("no geometry for", missing, file=sys.stderr)
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SITE / "static", OUT / "static")
    (OUT / "sources").mkdir(parents=True)
    shutil.copy(DATA / "sources/ets_2026_summary_sheets_redacted.pdf", OUT / CFG["survey_pdf"])
    write(OUT / "index.html", index_page())
    write(OUT / "methodology" / "index.html", methodology_page())
    for n in SEGS:
        write(OUT / SLUGS[n] / "index.html", segment_page(n))
    if a.dev:
        blog = ROOT.parent / "maxmautner" / "_site" / "index.html"
        m = re.search(r"<style>(.*?)</style>", blog.read_text(), re.S) if blog.exists() else None
        if m:
            write(DIST / CFG["site_css"].lstrip("/"), m.group(1))
        else:
            print("no built blog found for --dev stylesheet", file=sys.stderr)
    print(f"built index, methodology and {len(SEGS)} segment pages into {OUT} (version {VER})", file=sys.stderr)


if __name__ == "__main__":
    main()
