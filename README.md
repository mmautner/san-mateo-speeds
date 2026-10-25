# San Mateo speeds

How fast drivers actually go on San Mateo's surveyed streets, and what limits state law allows the city to set. Served at maxmautner.com/speeds/.

## Data

- `data/sources/ets_2026_summary_sheets_redacted.pdf`: City of San Mateo Engineering and Traffic Survey summary sheets (DKS Associates, August 2026), obtained through a public records request. One sheet per surveyed segment.
- `data/ets_2026_segments.csv` / `.json`: the 123 sheets as data (posted and recommended limits, 50th and 85th percentile speeds, 10 mph pace, survey date, daily volume, 2021–2025 collisions and rates, plus each sheet's description and recommendation text in the JSON).
- `data/city_document_conflicts.csv`: segments where the survey sheet disagrees with the city's Sept 22, 2026 Item 16 Attachment 3 or the ordinance adopted Oct 5, 2026. The survey sheet is treated as the source.

The sheets do not report sample sizes.

### Rebuilding

`pipeline/run.sh` renders the PDF, runs OCR (macOS Vision), parses each sheet, and applies a short list of hand corrections in `pipeline/fix.py`, each checked against the page image. Every row passes an arithmetic check: collisions ÷ (daily volume × 365 × 5 years × length) reproduces the sheet's printed collision rate.
