"""Parse Vision OCR boxes of ETS summary sheets into one record per page."""
import json, re, sys

d = json.load(open(sys.argv[1]))

def rows(obs, tol=0.007):
    obs = sorted(obs, key=lambda o: o["y"])
    out, cur = [], []
    for o in obs:
        if cur and abs(o["y"] - cur[0]["y"]) > tol:
            out.append(cur); cur = []
        cur.append(o)
    if cur: out.append(cur)
    return [sorted(r, key=lambda o: o["x0"]) for r in out]

def between(obs, x_lo, x_hi, y_lo, y_hi):
    sel = [o for o in obs if x_lo <= (o["x0"] + o["x1"]) / 2 < x_hi and y_lo < o["y"] < y_hi]
    return " ".join(o["t"] for r in rows(sel) for o in r).strip()

def ylabel(obs, pat):
    for o in obs:
        if re.search(pat, o["t"], re.I): return o["y"]
    return None

recs = []
for page, obs in sorted(d.items()):
    if len(obs) < 30: continue
    line = lambda y: " | ".join(o["t"] for o in obs if abs(o["y"] - y) < 0.008) if y else ""
    hdr = {}
    def cell(label_pat, x_lo, x_hi):
        y = ylabel(obs, label_pat)
        if y is None: return None
        v = between(obs, x_lo, x_hi, y - 0.008, y + 0.008)
        v = re.sub(label_pat, "", v, flags=re.I)
        return v.strip(" |:[]")
    r = {"page": int(page[1:])}
    r["street"] = cell(r"STREET NAME:", 0.25, 0.40)
    r["from"] = cell(r"^FROM:", 0.25, 0.40)
    r["to"] = cell(r"^TO:", 0.25, 0.40)
    r["direction"] = cell(r"DIRECTION:", 0.50, 0.70)
    r["length"] = cell(r"LENGTH:", 0.50, 0.70)
    r["bike_lanes"] = cell(r"BIKE LANES:", 0.50, 0.66)
    r["lanes"] = cell(r"NO\. LANES:", 0.80, 0.95)
    r["median"] = cell(r"MEDIAN:", 0.80, 0.95)
    r["existing"] = cell(r"EXISTING SPEED LIMIT:", 0.66, 0.85)
    r["recommended"] = cell(r"RECOMMENDED SPEED LIMIT:", 0.66, 0.85)
    r["p85"] = cell(r"85TH PERCENTILE:", 0.10, 0.39)
    r["p50"] = cell(r"50TH PERCENTILE:", 0.10, 0.39)
    r["survey_date"] = cell(r"DATE OF SURVEY:", 0.10, 0.39)
    r["pace"] = cell(r"10 MPH PACE:", 0.39, 0.62)
    r["pct_under"] = cell(r"PERCENT UNDER PACE:", 0.80, 0.95)
    r["pct_in"] = cell(r"PERCENT IN PACE:", 0.80, 0.95)
    r["pct_over"] = cell(r"PERCENT OVER PACE:", 0.80, 0.95)
    r["adt"] = cell(r"AVG DAILY VOLUME:", 0.24, 0.60)
    r["count_dates"] = cell(r"DATES OF COUNTS:", 0.80, 0.95)
    r["collisions"] = cell(r"TOTAL NO\.", 0.24, 0.33)
    r["statewide_rate"] = cell(r"STATEWIDE AVERAGE", 0.795, 0.95)
    r["actual_rate"] = cell(r"ACTUAL COLLISION RATE", 0.795, 0.95)
    r["collision_period"] = line(ylabel(obs, r"PERIOD:"))
    yd, yf, yc = ylabel(obs, r"^DESCRIPTION"), ylabel(obs, r"FACTORS CONSIDERED"), ylabel(obs, r"^CERTIFICATION")
    if yd and yf:
        r["description"] = between(obs, 0, 1, yd + 0.008, yf - 0.008)
    if yf and yc:
        r["factors"] = between(obs, 0, 0.40, yf + 0.008, yc - 0.008)
        r["recommendation_text"] = between(obs, 0.40, 1, yf + 0.008, yc - 0.008)
    r["min_conf"] = round(min(o["conf"] for o in obs), 2)
    recs.append(r)

json.dump(recs, open(sys.argv[2], "w"), indent=1)
print(len(recs))
