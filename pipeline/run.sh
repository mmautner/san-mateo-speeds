#!/usr/bin/env bash
# Rebuild data/ets_2026_segments.{csv,json} from the survey PDF. macOS only (uses the Vision framework for OCR).
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -x pipeline/.venv/bin/python ]] || { python3 -m venv pipeline/.venv; pipeline/.venv/bin/pip -q install -r pipeline/requirements.txt; }
PY=pipeline/.venv/bin/python
$PY pipeline/render.py
$PY pipeline/ocr.py build/png build/ocr.json
$PY pipeline/parse.py build/ocr.json build/recs.json
$PY pipeline/fix.py
$PY pipeline/legal.py
$PY pipeline/memo_tables.py
$PY pipeline/geometry.py
