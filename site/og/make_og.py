"""Open Graph preview images (1200x630): one per segment page, one for the index (also used by methodology).

    pipeline/.venv/bin/python site/og/make_og.py      # after build_site.py

Imports build_site so the numbers, labels and colors always match the pages.
"""
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent))
import build_site as B  # noqa: E402

OUT = B.OUT / "og"
W, H, PAD = 1200, 630, 72

# maxmautner.com dark tokens, and the map's validated dark-mode ordinal steps
BG, SURFACE = "#211e1b", "#2c2925"
TEXT, TEXT2, TEXT3, ACCENT = "#f1efe9", "#aaa39a", "#8a847b", "#c79045"
BIN_COLORS = ["#4cae5c", "#e3c53a", "#ef8a34", "#ec4f4a"]


def font(name, size, weight):
    f = ImageFont.truetype(str(HERE / "fonts" / name), size)
    # axes: Newsreader [wght, opsz]; IBM Plex Sans [wght, wdth]
    f.set_variation_by_axes([weight, min(72, size) if "Newsreader" in name else 100])
    return f


def wrap(d, text, f, width):
    lines, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if d.textlength(t, font=f) <= width or not cur: cur = t
        else: lines.append(cur); cur = w
    return lines + [cur]


def base():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - 10, W, H], fill=ACCENT)
    d.text((PAD, PAD - 6), "SAN MATEO SPEED SURVEY, 2026", font=font("IBMPlexSans.ttf", 22, 600), fill=TEXT3)
    return img, d


def footer(d, text):
    d.text((PAD, H - PAD + 6), text, font=font("IBMPlexSans.ttf", 24, 400), fill=TEXT3, anchor="ls")


def save(img, name):
    img.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(OUT / name, optimize=True)


def segment_image(n):
    s = B.SEGS[n]
    img, d = base()
    # street name, then the stretch
    for size in range(68, 47, -2):
        f = font("Newsreader.ttf", size, 600)
        if d.textlength(s["street"], font=f) <= W - 2 * PAD: break
    d.text((PAD, 160), s["street"], font=f, fill=TEXT, anchor="ls")
    sub = font("IBMPlexSans.ttf", 32, 400)
    stretch = f"{B.place(s['from'])} to {B.place(s['to'])}"
    stretch = stretch[0].upper() + stretch[1:]
    d.text((PAD, 208), wrap(d, stretch, sub, W - 2 * PAD)[0], font=sub, fill=TEXT2, anchor="ls")

    # three tiles: the limit, the median, the 85th
    tiles = [("Limit", s["existing"], None), ("Half of drivers go faster than", s["p50"], None),
             ("Fastest 15% go faster than", s["p85"], BIN_COLORS[B.bin_of(s)])]
    gap, top, th = 20, 250, 200
    tw = (W - 2 * PAD - 2 * gap) // 3
    lab, num, unit = font("IBMPlexSans.ttf", 26, 500), font("Newsreader.ttf", 108, 600), font("IBMPlexSans.ttf", 30, 500)
    for i, (label, v, mark) in enumerate(tiles):
        x = PAD + i * (tw + gap)
        d.rounded_rectangle([x, top, x + tw, top + th], radius=16, fill=SURFACE)
        for k, line in enumerate(wrap(d, label, lab, tw - 44)[:2]):
            d.text((x + 22, top + 40 + k * 32), line, font=lab, fill=TEXT2, anchor="ls")
        nx = x + 22
        d.text((nx, top + th - 28), str(v), font=num, fill=TEXT, anchor="ls")
        d.text((nx + d.textlength(str(v), font=num) + 10, top + th - 34), "mph", font=unit, fill=TEXT2, anchor="ls")
        if mark:  # same color key as the map: how far the 85th is over the limit
            d.rounded_rectangle([x, top + th - 8, x + tw, top + th], radius=4, fill=mark)

    if s["recommended"] > s["existing"]:
        line = f"The city's survey proposes raising the limit to {s['recommended']} mph."
    elif s["recommended"] < s["existing"]:
        line = f"The city's survey proposes lowering the limit to {s['recommended']} mph."
    else:
        line = f"The city's survey proposes keeping the limit at {s['recommended']} mph."
    d.text((PAD, top + th + 58), line, font=font("IBMPlexSans.ttf", 30, 500), fill=TEXT, anchor="ls")
    footer(d, f"maxmautner.com{B.BASE.rstrip('/')}")
    save(img, f"{B.SLUGS[n]}.png")


def index_image():
    img, d = base()
    f = font("Newsreader.ttf", 64, 600)
    y = 160
    for line in wrap(d, "How fast drivers go on San Mateo's surveyed streets", f, 640):
        d.text((PAD, y), line, font=f, fill=TEXT, anchor="ls"); y += 72
    n_inc = sum(1 for s in B.SEGS.values() if s["recommended"] > s["existing"])
    small = font("IBMPlexSans.ttf", 28, 400)
    y += 10
    for line in [f"{len(B.SEGS)} street segments measured.", f"On {n_inc}, the survey proposes raising the limit."]:
        d.text((PAD, y), line, font=small, fill=TEXT2, anchor="ls"); y += 40

    # citywide map of the segments, colored like the page map
    feats = [(B.bin_of(B.SEGS[n]), g["coords"]) for n, g in B.GEO.items() if "coords" in g]
    xs = [x for _, c in feats for x, _ in c]; ys = [y for _, c in feats for _, y in c]
    box = (760, 70, W - 40, H - 50)
    sx = (box[2] - box[0]) / ((max(xs) - min(xs)) * 0.79)  # cos(37.5 deg) keeps the city's shape
    sy = (box[3] - box[1]) / (max(ys) - min(ys))
    k = min(sx, sy)
    ox = box[0] + ((box[2] - box[0]) - (max(xs) - min(xs)) * 0.79 * k) / 2
    P = lambda c: (ox + (c[0] - min(xs)) * 0.79 * k, box[1] + (max(ys) - c[1]) * k)
    for b, c in sorted(feats, key=lambda t: t[0]):  # brightest (most over) drawn last
        d.line([P(p) for p in c], fill=BIN_COLORS[b], width=5, joint="curve")

    # legend
    leg = font("IBMPlexSans.ttf", 22, 400)
    lx, ly = PAD, y + 50
    d.text((lx, ly - 30), "Fastest 15% over the limit:", font=leg, fill=TEXT3, anchor="ls")
    for b, label in enumerate(["at or under", "1–4", "5–7", "8+ mph"]):
        d.rounded_rectangle([lx, ly - 14, lx + 26, ly - 6], radius=3, fill=BIN_COLORS[b])
        d.text((lx + 34, ly), label, font=leg, fill=TEXT2, anchor="ls")
        lx += 34 + d.textlength(label, font=leg) + 26
    footer(d, f"maxmautner.com{B.BASE.rstrip('/')}")
    save(img, "index.png")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index_image()
    ns = sorted(B.SEGS) if len(sys.argv) == 1 else [n for n in B.SEGS if B.SLUGS[n] in sys.argv[1:]]
    with ProcessPoolExecutor() as ex:
        list(ex.map(segment_image, ns, chunksize=16))
    print(f"wrote {len(ns) + 1} images to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
