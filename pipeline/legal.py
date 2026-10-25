"""Compute, per surveyed segment, the lowest speed limit California law allows the city to set.

Reads data/ets_2026_segments.json, writes data/legal_options.csv and .json. See docs/legal-memo.md for the rules.

Tiers, from most to least certain:
  rounding   CVC 22358.6(a)/(c): needs no finding. 85th at or just below a 5 mph step -> may round down one step.
  documented CVC 22358.6(b), only where the survey sheet itself applies it (CA MUTCD 2026 2B.21 para 12ac).
  possible   options whose criteria this data can't check (22358.7 extra reduction, 22358.8 retain/restore,
             22358.9 business activity district); listed with what is needed.
"""
import csv, json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
FLOOR = 20  # conservative floor; 22358(a) lists 15 mph, but we don't claim limits below 20 on these streets

PED_GEN = re.compile(r"high concentrations|school|preschool|daycare|park\b|senior|assisted living|medical|"
                     r"hospital|library|transit|caltrain|station|recreation|shopping center|trail", re.I)
APPLIED_B = re.compile(r"22358\.6\s*\(b\)")
APPLIED_C = re.compile(r"22358\.6\s*\(c\)")


def nearest5(x):
    return int(5 * ((x + 2.5) // 5))


def options(d):
    p85, existing, rec = d["p85"], d["existing"], d["recommended"]
    n = nearest5(p85)
    # CA MUTCD Table 2B-104(CA): an 85th within 2.5 mph at or below a step "rounds up" -> (c) applies;
    # above the step it "rounds down" -> (b) applies, with documented reasons.
    # CA MUTCD Table 2B-104(CA) groups an 85th exactly on a step (e.g. 45.0) with the "rounds up" rows, and the
    # survey applies 22358.6(c) to such segments, so an exact multiple of 5 is treated as rounding up.
    rounds_up = p85 <= n
    text = " ".join(filter(None, [d.get("factors"), d.get("recommendation_text"), d.get("description")]))
    factors = d.get("factors") or ""
    high_crash = d["actual_rate"] is not None and d["statewide_rate"] is not None and d["actual_rate"] > d["statewide_rate"]
    ped_gen = bool(PED_GEN.search(factors)) or "high concentrations" in text.lower()
    low = text.lower()
    reasons = [r for r, ok in [("collision rate above statewide average (CVC 627(b)(2))", high_crash),
                               ("pedestrian/bicyclist collision history (CVC 627(b)(2))",
                                "pedestrian/bicyclist collision" in low or "involved a pedestrian" in low
                                or "involved either a pedestrian" in low),
                               ("residential density (CVC 627(c)(1))", "residential density" in low),
                               ("pedestrian/bicyclist generator noted (CVC 627(c)(2))", ped_gen),
                               ("survey applied 22358.6(b)", bool(APPLIED_B.search(text)))] if ok]

    o = {"segment_no": d["segment_no"], "street": d["street"], "from": d["from"], "to": d["to"],
         "existing": existing, "recommended": rec, "p50": d["p50"], "p85": p85, "nearest_step": n,
         "survey_cites_b": bool(APPLIED_B.search(text)), "survey_cites_c": bool(APPLIED_C.search(text))}

    # tier 1: rounding alone
    if rounds_up:
        o["rounding_limit"], o["rounding_basis"] = n - 5, "22358.6(c)"
    else:
        o["rounding_limit"], o["rounding_basis"] = n, "22358.6(a)"

    # tier 2: plus reductions supported by conditions the sheet documents
    # CA MUTCD 2026 2B.21 para 12ac: a 22358.6(b) reduction needs written justification in the survey, approved by a
    # registered engineer. Count it as available only where the survey sheet itself applies it.
    lim, basis = o["rounding_limit"], [o["rounding_basis"]]
    survey_b = bool(APPLIED_B.search(text))
    if not rounds_up and survey_b:
        lim, basis = n - 5, ["22358.6(b)"]
    lim = max(lim, FLOOR, int(-(-(p85 - 12.4) // 5) * 5))  # 22358.6(e): no more than 12.4 below the 85th
    o["documented_limit"], o["documented_basis"] = lim, " + ".join(basis)
    o["documented_reasons"] = "; ".join(reasons)
    o["ped_generator_noted"] = ped_gen

    # tier 3: possible, with what is needed
    poss = []
    if not rounds_up and not survey_b:
        poss.append((max(n - 5, FLOOR), "22358.6(b)",
                     "the engineer documents written justification under CVC 627 (CA MUTCD 2B.21 para 12ac)"
                     + (f"; the sheet already lists: {'; '.join(reasons)}" if reasons else "")))
    seven_needs = ("a city finding that the limit is still more than is reasonable or safe, plus either a safety corridor "
                   "designation (CA MUTCD 2B.21 paras 12ai-12ar) or a generator of pedestrians or bicyclists within 1,320 ft "
                   "(Table 2B-105(CA)) on a segment in the city's top 20% for pedestrian/bicyclist deaths and serious "
                   "injuries over 3-5 years (paras 12at-12au)")
    if ped_gen:
        seven_needs += "; the survey sheet already notes a generator"
    poss.append((max(lim - 5, FLOOR), "22358.7", seven_needs))
    if existing < rec:
        poss.append((existing, "22358.8", "city confirms the current limit was set by an engineering and traffic survey, "
                     "and a registered engineer finds no general-purpose lanes added since"))
    lanes = d.get("lanes") or 0
    desc = (d.get("description") or "").lower()
    if lanes <= 4 and existing <= 30 and ("retail" in desc or "commercial" in desc) and "parking" in desc:
        poss.append((25 if existing > 25 else 20, "22358.9",
                     "commercial/downtown zoning, retail or dining on at least half the frontage, signals or stop signs "
                     "no more than 600 ft apart or uncontrolled marked crosswalks, and adjacent limits of 30 (for 25) or 25 (for 20)"))
    o["possible"] = [{"limit": a, "section": b, "needs": c} for a, b, c in poss if a is None or a < lim]
    o["lowest_possible"] = min([lim] + [p["limit"] for p in o["possible"] if p["limit"] is not None])
    return o


def main():
    segs = json.load(open(ROOT / "data/ets_2026_segments.json"))
    rows = [options(d) for d in segs]
    json.dump(rows, open(ROOT / "data/legal_options.json", "w"), indent=1)
    cols = ["segment_no", "street", "from", "to", "existing", "recommended", "p50", "p85", "nearest_step",
            "rounding_limit", "rounding_basis", "documented_limit", "documented_basis", "documented_reasons",
            "lowest_possible", "possible_summary", "survey_cites_b", "survey_cites_c"]
    with open(ROOT / "data/legal_options.csv", "w", newline="") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore"); w.writeheader()
        for r in rows:
            r2 = dict(r, possible_summary="; ".join(f"{p['limit']} via {p['section']} (needs {p['needs']})"
                                                     for p in r["possible"] if p["limit"] is not None))
            w.writerow(r2)
    return rows


if __name__ == "__main__":
    rows = main()
    print(len(rows), "segments")
