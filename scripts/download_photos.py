#!/usr/bin/env python3
"""Download every check-in photo from Untappd's S3 into originals/<checkin_id>.jpg.

Resumable: files that already exist are skipped. Re-run after exporting a fresh
CSV or JSON to pick up new check-ins.

Usage: python3 scripts/download_photos.py [export_path] [--workers N]
"""
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from checkins import load_checkins

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "originals")


def fetch(checkin_id, url, retries=3):
    dest = os.path.join(OUT, f"{checkin_id}.jpg")
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return checkin_id, "skip"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            tmp = dest + ".part"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
            return checkin_id, "ok"
        except Exception as e:
            err = str(e)
            time.sleep(1.5 * (attempt + 1))
    return checkin_id, f"fail: {err}"


def main():
    args = sys.argv[1:]
    workers = 6
    if "--workers" in args:
        workers = int(args[args.index("--workers") + 1])
    os.makedirs(OUT, exist_ok=True)
    paths = [a for a in args if a.endswith((".csv", ".json"))]
    rows, path = load_checkins(paths[0] if paths else None)
    rows = [r for r in rows if r["photo_url"]]
    print(f"{os.path.basename(path)}: {len(rows)} photos to check, {workers} workers")

    counts = {"ok": 0, "skip": 0, "fail": 0}
    failures = []
    with ThreadPoolExecutor(workers) as pool:
        futs = [pool.submit(fetch, r["checkin_id"], r["photo_url"]) for r in rows]
        for i, fut in enumerate(as_completed(futs), 1):
            cid, status = fut.result()
            key = status.split(":")[0]
            counts[key] += 1
            if key == "fail":
                failures.append((cid, status))
            if i % 100 == 0 or i == len(futs):
                print(f"{i}/{len(futs)} {counts}", flush=True)
    for cid, status in failures:
        print("FAILED", cid, status)


if __name__ == "__main__":
    main()
