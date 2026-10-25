"""Render each page of the ETS summary-sheet PDF to a grayscale PNG for OCR."""
import pathlib, sys
import pypdfium2

ROOT = pathlib.Path(__file__).resolve().parent.parent
pdf = pypdfium2.PdfDocument(ROOT / "data/sources/ets_2026_summary_sheets_redacted.pdf")
out = ROOT / "build/png"; out.mkdir(parents=True, exist_ok=True)
for i in range(len(pdf)):
    pdf[i].render(scale=200 / 72).to_pil().convert("L").save(out / f"p{i + 1:03d}.png")
print(len(pdf), "pages")
