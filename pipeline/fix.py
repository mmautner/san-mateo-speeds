"""Second pass: re-OCR blank or suspicious cells from enlarged crops, normalize, and validate."""
import csv, json, re, sys, pathlib, tempfile
from PIL import Image
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from ocr import ocr  # noqa: E402  (ocr.py guards its CLI below)

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
boxes = json.load(open(BUILD / "ocr.json"))
recs = json.load(open(BUILD / "recs.json"))

# label regex, x range of the value cell (normalized)
CELLS = {
    "street": (r"STREET NAME:", 0.25, 0.40), "from": (r"^FROM:", 0.25, 0.40), "to": (r"^TO:", 0.25, 0.40),
    "length": (r"LENGTH:", 0.50, 0.66), "lanes": (r"NO\. LANES:", 0.80, 0.95), "median": (r"MEDIAN:", 0.80, 0.95),
    "bike_lanes": (r"BIKE LANES:", 0.50, 0.66),
    "existing": (r"EXISTING SPEED LIMIT:", 0.66, 0.80), "recommended": (r"RECOMMENDED SPEED LIMIT:", 0.66, 0.80),
    "p85": (r"85TH PERCENTILE:", 0.16, 0.33), "p50": (r"50TH PERCENTILE:", 0.16, 0.33),
    "survey_date": (r"DATE OF SURVEY:", 0.16, 0.33), "pace": (r"10 MPH PACE:", 0.48, 0.58),
    "pct_under": (r"PERCENT UNDER PACE:", 0.80, 0.95), "pct_in": (r"PERCENT IN PACE:", 0.80, 0.95),
    "pct_over": (r"PERCENT OVER PACE:", 0.80, 0.95), "adt": (r"AVG DAILY VOLUME:", 0.16, 0.40),
    "collisions": (r"TOTAL NO\.", 0.16, 0.33), "statewide_rate": (r"STATEWIDE AVERAGE", 0.79, 0.95),
    "actual_rate": (r"ACTUAL COLLISION RATE", 0.79, 0.95),
}

def label_y(obs, pat):
    for o in obs:
        if re.search(pat, o["t"], re.I): return o["y"]

def reocr(page, field):
    pat, x0, x1 = CELLS[field]
    y = label_y(boxes[f"p{page:03d}"], pat)
    if y is None: return None
    im = Image.open(BUILD / f"png/p{page:03d}.png")
    W, H = im.size
    c = im.crop((int(x0 * W), int((y - 0.010) * H), int(x1 * W), int((y + 0.010) * H)))
    c = c.resize((c.width * 4, c.height * 4), Image.LANCZOS)
    canvas = Image.new("L", (c.width + 200, c.height + 200), 255); canvas.paste(c, (100, 100))
    with tempfile.NamedTemporaryFile(suffix=".png", dir=BUILD) as f:
        canvas.save(f.name)
        return " ".join(o["t"] for o in sorted(ocr(f.name), key=lambda o: o["x0"])).strip(" |[]")

def reocr_box(page, top_pat, bottom_pat, x0, x1, scale=2):
    """OCR a multi-line text box between two section labels; first-pass OCR drops lines here."""
    obs = boxes[f"p{page:03d}"]
    y0, y1 = label_y(obs, top_pat), label_y(obs, bottom_pat)
    if y0 is None or y1 is None: return None
    im = Image.open(BUILD / f"png/p{page:03d}.png")
    W, H = im.size
    c = im.crop((int(x0 * W), int((y0 + 0.012) * H), int(x1 * W), int((y1 - 0.010) * H)))
    c = c.resize((c.width * scale, c.height * scale), Image.LANCZOS)
    with tempfile.NamedTemporaryFile(suffix=".png", dir=BUILD) as f:
        c.save(f.name)
        res = ocr(f.name)
    lines = []
    for o in sorted(res, key=lambda o: o["y"]):
        if lines and abs(o["y"] - lines[-1][0]) < 0.01: lines[-1][1].append(o)
        else: lines.append((o["y"], [o]))
    return " ".join(" ".join(t["t"] for t in sorted(l, key=lambda t: t["x0"])) for _, l in lines)

def num(s, kind=float):
    if s is None: return None
    s = re.sub(r"^.*(:|NO\.I?)", "", s).replace(",", "")
    m = re.search(r"\d+(\.\d+)?", s)
    return kind(m.group()) if m else None

MON = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
def date(s):
    if not s: return None
    s = s.translate(str.maketrans({"А": "A", "р": "p", "г": "r", "Р": "P"})).replace("Ju1", "Jul").replace(" ", "")
    m = re.search(r"(\d{1,2})-([A-Za-z]{3})-(\d{2})", s)
    return f"20{m.group(3)}-{MON[m.group(2).title()]:02d}-{int(m.group(1)):02d}" if m else None

def write(rows):
    for o in rows: o["segment_no"] = o["page"] - 1
    json.dump(rows, open(ROOT / "data/ets_2026_segments.json", "w"), indent=1)
    cols = ["segment_no", "page", "street", "from", "to", "direction", "length_mi", "lanes", "median", "bike_lanes",
            "existing", "recommended", "p50", "p85", "pace", "pct_under", "pct_in", "pct_over", "survey_date",
            "count_date", "adt", "collisions", "statewide_rate", "actual_rate"]
    with open(ROOT / "data/ets_2026_segments.csv", "w", newline="") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)

def clean_name(s):
    if not s: return s
    s = s.lstrip("_ ").replace("Bivd", "Blvd").replace(" PI", " Pl").replace("EI ", "El ").replace("2nc ", "2nd ")
    s = re.sub(r"\b([NSEW])(?=[A-Z][a-z])", r"\1 ", s)          # "WHillsdale" -> "W Hillsdale"
    s = re.sub(r"^([NS])BSt$", r"\1 B St", s)
    s = re.sub(r"\bs (?=[A-Z])", "S ", s); s = re.sub(r"\bst$", "St", s)
    return s

log = []
out = []
for r in recs:
    p = r["page"]
    for f in CELLS:
        v = r.get(f)
        if not v or (f in ("p85", "p50", "existing", "recommended") and not re.search(r"\d", v)):
            nv = reocr(p, f); log.append((p, f, v, nv)); r[f] = nv
    o = {
        "page": p,
        "street": clean_name(r["street"]), "from": clean_name(r["from"]), "to": clean_name(r["to"]),
        "direction": r.get("direction"), "length_mi": num(r["length"]), "lanes": num(r["lanes"], int),
        "median": (r.get("median") or "").strip()[:1] or None, "bike_lanes": (r.get("bike_lanes") or "").strip()[:1] or None,
        "existing": num(r["existing"], int), "recommended": num(r["recommended"], int),
        "p50": num(r["p50"], int), "p85": num(r["p85"], int),
        "pace": re.sub(r"\s*-\s*", "-", r.get("pace") or "") or None,
        "pct_under": num(r["pct_under"], int), "pct_in": num(r["pct_in"], int), "pct_over": num(r["pct_over"], int),
        "survey_date": date(r["survey_date"]), "count_date": date(r.get("count_dates")),
        "adt": num(r["adt"], int), "collisions": num(r["collisions"], int),
        "statewide_rate": num(r["statewide_rate"]), "actual_rate": num(r["actual_rate"]),
        "description": r.get("description"), "factors": r.get("factors"), "recommendation_text": r.get("recommendation_text"),
    }
    out.append(o)

# validation
probs = []
for o in out:
    p = o["page"]
    for k in ("street", "from", "to", "existing", "recommended", "p50", "p85", "survey_date", "adt", "collisions", "length_mi", "actual_rate"):
        if o[k] is None: probs.append((p, k, "missing"))
    if o["length_mi"] is not None and not (0.05 <= o["length_mi"] <= 3): probs.append((p, "length", o["length_mi"]))
    if o["p50"] and o["p85"] and not (o["p50"] <= o["p85"]): probs.append((p, "p50>p85", o["p50"], o["p85"]))
    if None not in (o["pct_under"], o["pct_in"], o["pct_over"]):
        s = o["pct_under"] + o["pct_in"] + o["pct_over"]
        if abs(s - 100) > 1: probs.append((p, "pct sum", s))
    if o["pace"]:
        m = re.match(r"(\d+)-(\d+)$", o["pace"])
        if not m or int(m.group(2)) - int(m.group(1)) != 9: probs.append((p, "pace", o["pace"]))
    if None not in (o["collisions"], o["adt"], o["length_mi"], o["actual_rate"]) and o["adt"] and o["length_mi"]:
        rate = o["collisions"] * 1e6 / (o["adt"] * 365 * 5 * o["length_mi"])
        if abs(rate - o["actual_rate"]) > max(0.03, 0.03 * o["actual_rate"]): probs.append((p, "rate", round(rate, 2), o["actual_rate"], o["collisions"], o["adt"], o["length_mi"]))
    for k in ("existing", "recommended"):
        if o[k] and o[k] % 5: probs.append((p, k, o[k]))

write(out)
print("re-OCR count:", len(log))
print("problems:"); [print("  ", x) for x in probs]

# --- manual corrections, each verified by eye against the page image ---
for o in out:
    p = o["page"]
    o["factors"] = reocr_box(p, r"FACTORS CONSIDERED", r"^CERTIFICATION", 0.055, 0.405) or o["factors"]
    o["recommendation_text"] = reocr_box(p, r"RECOMMENDATIONS", r"^CERTIFICATION", 0.405, 0.94) or o["recommendation_text"]
    o["description"] = reocr_box(p, r"^DESCRIPTION", r"FACTORS CONSIDERED", 0.055, 0.94) or o["description"]

MANUAL = {
    19: {"street": "Dartmouth/W 4th Ave", "from": "W 5th Ave"},
    **{p: {"collisions": 0} for p in (39, 43, 114, 116, 117)},
    **{p: {"length_mi": v} for p, v in {3: .85, 15: .25, 18: .54, 38: .62, 50: .53, 70: .6, 71: .48, 74: .22, 80: .17,
                                         84: .48, 85: .35, 94: .6, 99: .43, 100: .65, 101: .35, 102: .44, 109: .72, 111: .67,
                                         62: .47, 114: .12, 116: .13, 117: .11}.items()},
}
for o in out:
    o.update(MANUAL.get(o["page"], {}))
write(out)

# cross-check speed fields against the narrative recommendation text
print("cross-checks:")
for o in out:
    t = (o["recommendation_text"] or "").replace("–", "-")
    m = re.search(r"85th-percentile speed is (\d+)", t)
    if not m or int(m.group(1)) != o["p85"]: print("   p85", o["page"], o["p85"], m and m.group(1))
    m = re.search(r"recommended speed limit is (\d+)", t, re.I)
    if not m or int(m.group(1)) != o["recommended"]: print("   rec", o["page"], o["recommended"], m and m.group(1))
    m = re.search(r"pace is (\d+)\s*-\s*(\d+)", t)
    if m and o["pace"] != f"{m.group(1)}-{m.group(2)}": print("   pace", o["page"], o["pace"], m.groups())
    lo, hi = map(int, o["pace"].split("-")) if o["pace"] and re.match(r"\d+-\d+$", o["pace"]) else (0, 999)
    if not (lo - 1 <= o["p50"] <= hi + 1): print("   p50 outside pace", o["page"], o["p50"], o["pace"])
    if o["p85"] - o["p50"] > 9 or o["p85"] - o["p50"] < 1: print("   spread", o["page"], o["p50"], o["p85"])
