# San Mateo speeds

How fast drivers actually go on San Mateo's surveyed streets, and what limits state law allows the city to set. Served at maxmautner.com/speeds/.

## Data

- `data/sources/ets_2026_summary_sheets_redacted.pdf`: City of San Mateo Engineering and Traffic Survey summary sheets (DKS Associates, August 2026), obtained through a public records request. One sheet per surveyed segment.
- `data/ets_2026_segments.csv` / `.json`: the 123 sheets as data (posted and recommended limits, 50th and 85th percentile speeds, 10 mph pace, survey date, daily volume, 2021–2025 collisions and rates, plus each sheet's description and recommendation text in the JSON).
- `data/city_document_conflicts.csv`: segments where the survey sheet disagrees with the city's Sept 22, 2026 Item 16 Attachment 3 or the ordinance adopted Oct 5, 2026. The survey sheet is treated as the source.

The sheets do not report sample sizes.

### Rebuilding

`pipeline/run.sh` renders the PDF, runs OCR (macOS Vision), parses each sheet, and applies a short list of hand corrections in `pipeline/fix.py`, each checked against the page image. Every row passes an arithmetic check: collisions ÷ (daily volume × 365 × 5 years × length) reproduces the sheet's printed collision rate.

## Legal options

`pipeline/legal.py` computes, for each segment, the lowest limit state law allows using rounding alone (CVC 22358.6(c)) or reductions the survey itself documents (22358.6(b)), and lists further options (22358.7, 22358.8, 22358.9) with what each would need. Output: `data/legal_options.csv` / `.json`. The reasoning and citations are in `docs/legal-memo.md` (built from `docs/legal-memo-body.md` by `pipeline/memo_tables.py`).

## Site

`build_site.py` writes the page to `dist/san-mateo-speeds/` from the files in `data/`. `pipeline/geometry.py` draws each segment on the OpenStreetMap street network (`data/sources/geo/`, © OpenStreetMap contributors, ODbL) and writes `data/segments_geo.json`.

`./deploy.sh` builds and uploads to `s3://maxmautner.com/san-mateo-speeds/`, then invalidates that path on CloudFront. It never deletes anything. The blog's `s3_website.yml` must list `^san-mateo-speeds/` under `ignore_on_server`, or a blog deploy will delete this prefix.
