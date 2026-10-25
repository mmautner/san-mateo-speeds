"""Build docs/legal-memo.md from docs/legal-memo-body.md plus tables from data/legal_options.json."""
import contextlib, io
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = json.load(open(ROOT / "data/legal_options.json"))


def seg(r):
    return f"{r['street']}, {r['from']} – {r['to']}"


def possible(r):
    return "; ".join(f"{p['limit']} ({p['section']})" for p in r["possible"] if p["limit"] is not None) or "—"


def table(rows, title):
    print(f"\n#### {title}\n")
    print("| PDF p. | Segment | Posted | Proposed | 50th | 85th | Lowest now (section) | Possibly lower (section) |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['segment_no'] + 1} | {seg(r)} | {r['existing']} | {r['recommended']} | {r['p50']} | {r['p85']} | "
              f"{r['documented_limit']} ({r['documented_basis']}) | {possible(r)} |")


inc = [r for r in R if r["recommended"] > r["existing"]]
rest = [r for r in R if r["recommended"] <= r["existing"]]
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    table(inc, f"Segments with a proposed increase ({len(inc)})")
    table(rest, f"All other surveyed segments ({len(rest)})")
body = (ROOT / "docs/legal-memo-body.md").read_text()
(ROOT / "docs/legal-memo.md").write_text(body.replace("{{TABLES}}", buf.getvalue().strip()))
