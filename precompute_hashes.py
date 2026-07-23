#!/usr/bin/env python3
"""
Salaryse Asset Finder — reverse-image-search precompute.

Renders every AppImages image as ONE Chrome-headless contact sheet
(transparent background, faithful SVG rendering incl. currentColor), slices it,
and computes a 256-bit dHash fingerprint per image -> hashes.json.

Run with the venv python:
    ./venv/bin/python precompute_hashes.py

Nothing is written into the app repo. Needs Google Chrome installed.
"""

import re, os, sys, json, math, subprocess, io, base64, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
# Path to the salary_se_app checkout (override with SALARYSE_APP env var)
REPO = os.environ.get("SALARYSE_APP", "/Users/ashvintiwari/Desktop/salaryse/salary_se_app")
# Chrome/Chromium binary (override with CHROME_BIN env var; Linux/CI differs)
CHROME = os.environ.get("CHROME_BIN", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
SHEET_HTML = os.path.join(HERE, "_sheet.html")
SHEET_PNG = os.path.join(HERE, "_sheet.png")
OUT = os.path.join(HERE, "hashes.json")
THUMBS_OUT = os.path.join(HERE, "thumbs.json")   # name -> embedded thumbnail data-URI
LOTTIE_LIB = os.path.join(HERE, "lottie.min.js")
LOTTIE_SIGS_OUT = os.path.join(HERE, "lottie_sigs.json")  # name -> structural signature
LOTTIE_BATCH = 12

CELL = 64          # px per cell
COLS = 16          # cells per row
BATCH = 120        # images per Chrome render (small enough to fully load)
ASSET_PREFIX = "assets/"
NETWORK_PREFIX = "https://assets.salaryse.com/"
CONST_RE = re.compile(r'static const\s+(\w+)\s*=\s*([^;]*?);', re.DOTALL)
STRING_RE = re.compile(r'"([^"]*)"')

LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None


def parse_items():
    with open(os.path.join(REPO, "lib/util/constants/app_images.dart"), encoding="utf-8") as f:
        text = "\n".join(l for l in f.read().splitlines() if not l.strip().startswith("//"))
    seen = {}
    for name, raw in CONST_RE.findall(text):
        if name in ("assetImagePath", "networkImagePath"):
            continue
        m = STRING_RE.search(raw)
        if not m:
            continue
        path = m.group(1).replace("${assetImagePath}", ASSET_PREFIX).replace("${networkImagePath}", NETWORK_PREFIX)
        ext = (re.search(r'\.(\w+)(?:\?|$)', path) or [None, "?"])[1]
        if ext == "json":                       # lottie -> not a still image
            continue
        ref = path if path.startswith("http") else "file://" + os.path.join(REPO, path)
        seen[name] = {"name": name, "ref": ref}
    items = list(seen.values())
    return items[:LIMIT] if LIMIT else items


def render_batch(chunk, html_path, png_path):
    rows = math.ceil(len(chunk) / COLS)
    w, h = COLS * CELL, rows * CELL
    cells = "".join(f'<div class=c><img src="{it["ref"]}" referrerpolicy="no-referrer"></div>' for it in chunk)
    doc = (f'<!doctype html><meta charset=utf-8>'
           f'<style>*{{margin:0;padding:0}}body{{width:{w}px;background:transparent;'
           f'display:flex;flex-wrap:wrap}}'
           f'.c{{width:{CELL}px;height:{CELL}px;display:flex;align-items:center;justify-content:center}}'
           f'.c img{{max-width:100%;max-height:100%;object-fit:contain}}</style>{cells}')
    with open(html_path, "w") as f:
        f.write(doc)
    if os.path.exists(png_path):
        os.remove(png_path)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=1", "--default-background-color=00000000",
                    "--virtual-time-budget=60000", f"--screenshot={png_path}",
                    f"--window-size={w},{h}", f"file://{html_path}"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.exists(png_path)


import math as _math


def _resize_bilinear(px, W, H, TW=17, TH=16):
    """Hand-written bilinear resize -> flat float list. MUST match the JS version."""
    out = []
    for ty in range(TH):
        sy = (ty + 0.5) * H / TH - 0.5
        y0 = _math.floor(sy); fy = sy - y0
        y0c = min(max(y0, 0), H - 1); y1c = min(max(y0 + 1, 0), H - 1)
        for tx in range(TW):
            sx = (tx + 0.5) * W / TW - 0.5
            x0 = _math.floor(sx); fx = sx - x0
            x0c = min(max(x0, 0), W - 1); x1c = min(max(x0 + 1, 0), W - 1)
            v00 = px[y0c * W + x0c]; v10 = px[y0c * W + x1c]
            v01 = px[y1c * W + x0c]; v11 = px[y1c * W + x1c]
            top = v00 * (1 - fx) + v10 * fx
            bot = v01 * (1 - fx) + v11 * fx
            out.append(top * (1 - fy) + bot * fy)
    return out


def canonicalize(g):
    """g: 'L' image -> polarity-normalised, trimmed, min-max stretched, 17x16 floats."""
    from PIL import ImageOps
    W, H = g.size
    px = g.load()
    border = n = 0
    for x in range(W):
        border += px[x, 0] + px[x, H - 1]; n += 2
    for y in range(H):
        border += px[0, y] + px[W - 1, y]; n += 2
    if border / n < 128:
        g = ImageOps.invert(g)
    mask = g.point(lambda p: 255 if p < 240 else 0)
    bbox = mask.getbbox()
    if bbox:
        g = g.crop(bbox)
    W, H = g.size
    flat = list(g.getdata())
    mn, mx = min(flat), max(flat)
    if mx > mn:
        sc = 255.0 / (mx - mn)
        flat = [(v - mn) * sc for v in flat]
    return _resize_bilinear(flat, W, H)


def dhash_of_cell(cell):
    """cell: RGBA PIL image. Returns 64-hex-char hash, or None if blank."""
    from PIL import Image, ImageStat
    white = Image.alpha_composite(Image.new("RGBA", cell.size, (255, 255, 255, 255)), cell).convert("L")
    g = white
    if ImageStat.Stat(white).stddev[0] < 6:          # colourless on white -> use silhouette
        alpha = cell.split()[3]
        if ImageStat.Stat(alpha).stddev[0] < 3:
            return None                              # genuinely empty cell
        g = alpha
    vals = canonicalize(g)                           # 17*16 floats
    val = 0
    for row in range(16):
        for col in range(16):
            i = row * 17 + col
            val = (val << 1) | (1 if vals[i] < vals[i + 1] else 0)
    return f"{val:064x}"


def placeholder_hash():
    """Hash of Chrome's broken-image glyph, so we can skip cells that didn't load."""
    from PIL import Image
    ok = render_batch([{"ref": "file:///does/not/exist.png"}],
                      SHEET_HTML + ".ph.html", SHEET_PNG + ".ph.png")
    if not ok:
        return None
    sheet = Image.open(SHEET_PNG + ".ph.png").convert("RGBA")
    return dhash_of_cell(sheet.crop((0, 0, CELL, CELL)))


def make_thumb(cell):
    """Small embedded WebP data-URI so previews render instantly with no network."""
    t = cell.resize((48, 48), 1)             # 1 = BILINEAR
    buf = io.BytesIO()
    t.save(buf, "WEBP", quality=80, method=4)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def hash_chunk(chunk, base_index, hashes, thumbs, ph):
    from PIL import Image
    html_path = f"{SHEET_HTML}.{base_index}.html"
    png_path = f"{SHEET_PNG}.{base_index}.png"
    if not render_batch(chunk, html_path, png_path):
        return list(range(len(chunk)))          # whole chunk failed to render
    sheet = Image.open(png_path).convert("RGBA")
    failed = []
    for j, it in enumerate(chunk):
        col, row = j % COLS, j // COLS
        cell = sheet.crop((col * CELL, row * CELL, col * CELL + CELL, row * CELL + CELL))
        hh = dhash_of_cell(cell)
        if hh is None or hh == ph:
            failed.append(j)
            continue
        hashes[it["name"]] = hh
        thumbs[it["name"]] = make_thumb(cell)
    os.remove(html_path); os.remove(png_path)
    return failed


def parse_lottie():
    with open(os.path.join(REPO, "lib/util/constants/app_images.dart"), encoding="utf-8") as f:
        text = "\n".join(l for l in f.read().splitlines() if not l.strip().startswith("//"))
    seen = {}
    for name, raw in CONST_RE.findall(text):
        if name in ("assetImagePath", "networkImagePath"):
            continue
        m = STRING_RE.search(raw)
        if not m:
            continue
        path = m.group(1).replace("${assetImagePath}", ASSET_PREFIX).replace("${networkImagePath}", NETWORK_PREFIX)
        if not path.endswith(".json"):
            continue
        seen[name] = {"name": name,
                      "url": path if path.startswith("http") else None,
                      "local": None if path.startswith("http") else os.path.join(REPO, path)}
    return list(seen.values())


def fetch_lottie(item):
    try:
        if item["url"]:
            req = urllib.request.Request(item["url"], headers={"User-Agent": "asset-finder"})
            return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        if os.path.exists(item["local"]):
            return open(item["local"], encoding="utf-8").read()
    except Exception:
        return None
    return None


def lottie_sig(d):
    """Structural signature — same animation exported twice -> same signature.
    MUST match lottieSig() in the gallery JS."""
    w = int(d.get("w", 0) or 0); h = int(d.get("h", 0) or 0)
    fr = round(float(d.get("fr", 0) or 0)); op = round(float(d.get("op", 0) or 0)); ip = round(float(d.get("ip", 0) or 0))
    layers = d.get("layers", []) or []
    names = "~".join(sorted(str(l.get("nm", "")) for l in layers))
    assets = len(d.get("assets", []) or [])
    return f"{w}x{h}|fr{fr}|ip{ip}|op{op}|L{len(layers)}|A{assets}|{names}"


def render_lottie_batch(batch, lib, html_path, png_path):
    import urllib.request
    rows = math.ceil(len(batch) / COLS)
    w, h = COLS * CELL, rows * CELL
    arr = ",".join(b["data"] for b in batch)
    doc = (f'<!doctype html><meta charset=utf-8>'
           f'<style>*{{margin:0;padding:0}}#g{{width:{w}px;display:flex;flex-wrap:wrap}}'
           f'.c{{width:{CELL}px;height:{CELL}px}}</style><div id=g></div>'
           f'<script>{lib}</script><script>'
           f'var D=[{arr}];var done=0;'
           f'D.forEach(function(ad){{var c=document.createElement("div");c.className="c";'
           f'document.getElementById("g").appendChild(c);'
           f'var a=lottie.loadAnimation({{container:c,renderer:"svg",loop:false,autoplay:false,animationData:ad}});'
           f'a.addEventListener("DOMLoaded",function(){{a.goToAndStop(Math.floor(a.totalFrames*0.5),true);'
           f'done++;if(done===D.length)document.title="OK";}});}});</script>')
    with open(html_path, "w") as f:
        f.write(doc)
    if os.path.exists(png_path):
        os.remove(png_path)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=1", "--default-background-color=00000000",
                    "--virtual-time-budget=30000", f"--screenshot={png_path}",
                    f"--window-size={w},{h}", f"file://{html_path}"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.exists(png_path)


def do_lottie(hashes, thumbs):
    from PIL import Image
    from concurrent.futures import ThreadPoolExecutor
    if not os.path.exists(LOTTIE_LIB):
        print("  (lottie.min.js missing -> skipping lottie)"); return {}
    lib = open(LOTTIE_LIB).read()
    items = parse_lottie()
    print(f"lottie: {len(items)} animations; fetching JSON...")
    sigs = {}
    ready = []
    def load(it):
        raw = fetch_lottie(it)
        if not raw:
            return None
        try:
            d = json.loads(raw)
        except Exception:
            return None
        return (it, raw, lottie_sig(d))
    for res in ThreadPoolExecutor(max_workers=16).map(load, items):
        if res:
            it, raw, sig = res
            sigs[it["name"]] = sig
            ready.append({"name": it["name"], "data": raw})
    print(f"lottie: {len(ready)} fetched; rendering frames...")
    for start in range(0, len(ready), LOTTIE_BATCH):
        batch = ready[start:start + LOTTIE_BATCH]
        hp, pp = f"{SHEET_HTML}.lot{start}.html", f"{SHEET_PNG}.lot{start}.png"
        if not render_lottie_batch(batch, lib, hp, pp):
            continue
        sheet = Image.open(pp).convert("RGBA")
        for j, b in enumerate(batch):
            col, row = j % COLS, j // COLS
            cell = sheet.crop((col * CELL, row * CELL, col * CELL + CELL, row * CELL + CELL))
            hh = dhash_of_cell(cell)
            if hh:
                hashes[b["name"]] = hh
                thumbs[b["name"]] = make_thumb(cell)
        os.remove(hp); os.remove(pp)
    with open(LOTTIE_SIGS_OUT, "w") as f:
        json.dump(sigs, f)
    print(f"lottie: {len(sigs)} signatures -> {LOTTIE_SIGS_OUT}")
    return sigs


def main():
    items = parse_items()
    print(f"{len(items)} images (lottie excluded); rendering in batches of {BATCH}...")
    ph = placeholder_hash()
    hashes, thumbs = {}, {}
    still_failed = 0
    for start in range(0, len(items), BATCH):
        chunk = items[start:start + BATCH]
        failed = hash_chunk(chunk, start, hashes, thumbs, ph)
        # one retry for cells that showed the placeholder (slow network)
        if failed:
            retry = [chunk[j] for j in failed]
            f2 = hash_chunk(retry, start + 100000, hashes, thumbs, ph)
            still_failed += len(f2)
        print(f"  {min(start + BATCH, len(items))}/{len(items)} done "
              f"({len(hashes)} hashed, {still_failed} failed)")

    do_lottie(hashes, thumbs)          # adds lottie frames to hashes + thumbs

    with open(OUT, "w") as f:
        json.dump(hashes, f)
    with open(THUMBS_OUT, "w") as f:
        json.dump(thumbs, f)
    print(f"DONE: {len(hashes)} hashes -> {OUT}  ({still_failed} could not be loaded)")
    print(f"      {len(thumbs)} embedded thumbnails -> {THUMBS_OUT}")


if __name__ == "__main__":
    main()
