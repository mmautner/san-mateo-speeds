"""OCR each rendered ETS summary sheet with macOS Vision; dump text boxes as JSON."""
import json, sys, pathlib
import Vision, Quartz
from Foundation import NSURL

def ocr(path):
    url = NSURL.fileURLWithPath_(str(path))
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(False)
    h = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None)
    h.performRequests_error_([req], None)
    out = []
    for o in req.results():
        c = o.topCandidates_(1)[0]
        b = o.boundingBox()  # normalized, origin bottom-left
        out.append({"t": c.string(), "x0": b.origin.x, "x1": b.origin.x + b.size.width,
                    "y": 1 - (b.origin.y + b.size.height / 2), "conf": c.confidence()})
    return out

if __name__ == "__main__":
    pngdir, outpath = pathlib.Path(sys.argv[1]), sys.argv[2]
    res = {p.stem: ocr(p) for p in sorted(pngdir.glob("p*.png"))}
    json.dump(res, open(outpath, "w"))
    print(len(res))
