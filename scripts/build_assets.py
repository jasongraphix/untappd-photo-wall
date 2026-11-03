#!/usr/bin/env python3
"""Turn originals/ into the web assets the gallery needs (requires ImageMagick).

  build/tiles/<id>.png      64px square crops (intermediate)
  site/img/m/<id>.webp      360px square crops, loaded on hover
  site/img/atlas-N.webp     sprite sheets of the 64px tiles (COLS x ROWS each)
  site/data/beers.json      slim per-photo metadata, ordered to match the atlas

Page settings (the title) come from config.json, overridden by config.local.json.

Photos are ordered oldest to newest; tile i lives in atlas i // PER_ATLAS at
column (i % PER_ATLAS) % COLS, row (i % PER_ATLAS) // COLS.
Re-runnable: existing thumbnails are skipped.
"""
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from checkins import load_checkins

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIG = os.path.join(ROOT, "originals")
TILES = os.path.join(ROOT, "build", "tiles")
MED = os.path.join(ROOT, "site", "img", "m")
IMG = os.path.join(ROOT, "site", "img")
DATA = os.path.join(ROOT, "site", "data")

TILE = 64
MEDIUM = 360
COLS = 32
ROWS = 38
PER_ATLAS = COLS * ROWS


def load_config():
    cfg = {"title": "My Beer Wall"}
    for name in ("config.json", "config.local.json"):
        path = os.path.join(ROOT, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                cfg.update(json.load(f))
    return cfg


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def make_thumbs(cid):
    src = os.path.join(ORIG, f"{cid}.jpg")
    med = os.path.join(MED, f"{cid}.webp")
    tile = os.path.join(TILES, f"{cid}.png")
    if not os.path.exists(med):
        run(["magick", src, "-auto-orient", "-thumbnail", f"{MEDIUM}x{MEDIUM}^",
             "-gravity", "center", "-extent", f"{MEDIUM}x{MEDIUM}",
             "-strip", "-quality", "78", med])
    if not os.path.exists(tile):
        run(["magick", med, "-thumbnail", f"{TILE}x{TILE}!", "-strip", tile])
    return cid


def num(v):
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except ValueError:
        return None


def main():
    for d in (TILES, MED, IMG, DATA):
        os.makedirs(d, exist_ok=True)

    everything, export_path = load_checkins(sys.argv[1] if len(sys.argv) > 1 else None)
    print("reading", os.path.basename(export_path))
    rows = [r for r in everything if r["photo_url"]]
    rows.sort(key=lambda r: r["created_at_utc"])
    rows = [r for r in rows if os.path.exists(os.path.join(ORIG, f"{r['checkin_id']}.jpg"))]
    print(f"{len(rows)} photos")

    ids = [r["checkin_id"] for r in rows]
    with ThreadPoolExecutor(os.cpu_count() or 4) as pool:
        for i, _ in enumerate(pool.map(make_thumbs, ids), 1):
            if i % 200 == 0:
                print(f"thumbs {i}/{len(ids)}", flush=True)

    n_atlas = (len(ids) + PER_ATLAS - 1) // PER_ATLAS
    for a in range(n_atlas):
        chunk = ids[a * PER_ATLAS:(a + 1) * PER_ATLAS]
        files = [os.path.join(TILES, f"{c}.png") for c in chunk]
        out = os.path.join(IMG, f"atlas-{a}.webp")
        run(["magick", "montage", *files, "-tile", f"{COLS}x", "-geometry", f"{TILE}x{TILE}+0+0",
             "-background", "#111", "-quality", "80", out])
        print("wrote", out, os.path.getsize(out) // 1024, "KB")

    # A photo check-in left unrated borrows the beer's rating from any other check-in of it.
    rated = {}
    for r in sorted(everything, key=lambda r: r["created_at_utc"]):
        if num(r["rating_score"]):
            rated[r["bid"]] = num(r["rating_score"])
    for r in rows:
        if not num(r["rating_score"]) and r["bid"] in rated:
            r["rating_score"] = str(rated[r["bid"]])

    beers = []
    for r in rows:
        beers.append({
            "id": int(r["checkin_id"]),
            "bid": int(r["bid"]),
            "name": r["beer_name"],
            "brewery": r["brewery_name"],
            "style": r["beer_type"],
            "abv": num(r["beer_abv"]),
            "rating": num(r["rating_score"]),
            "global": num(r["global_rating_score"]),
            "date": r["created_at"][:10],
            "venue": r["venue_name"] or None,
            "city": r["venue_city"] or None,
            "state": r["venue_state"] or None,
            "country": r["venue_country"] or None,
            "home": r["venue_name"] == "Untappd at Home",
            "comment": r["comment"] or None,
        })
    # Changes whenever the set of photos changes, so re-uploads bypass browser caches.
    version = hashlib.md5(",".join(ids).encode()).hexdigest()[:8]
    meta = {"tile": TILE, "cols": COLS, "rows": ROWS, "perAtlas": PER_ATLAS,
            "atlases": n_atlas, "medium": MEDIUM, "version": version,
            "title": load_config()["title"]}
    with open(os.path.join(DATA, "beers.json"), "w") as f:
        json.dump({"meta": meta, "beers": beers}, f, separators=(",", ":"), ensure_ascii=False)
    print("wrote beers.json", os.path.getsize(os.path.join(DATA, "beers.json")) // 1024, "KB")


if __name__ == "__main__":
    main()
