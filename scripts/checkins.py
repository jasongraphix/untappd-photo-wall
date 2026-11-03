"""Load an Untappd export (CSV or JSON) as a list of check-in dicts.

Both formats carry the same fields. This module returns rows shaped like the CSV
(every value a string, missing values ""), so the rest of the pipeline never needs
to know which format came in.

The export is found automatically: the most recently modified .csv or .json in the
project root that looks like an Untappd check-in export. JSON exports come down with
random file names, so the file name doesn't matter.
"""
import csv
import glob
import json
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIRED = {"checkin_id", "beer_name", "created_at"}


def _read_json(path):
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, list) or not data or not REQUIRED <= set(data[0]):
        raise ValueError("not an Untappd check-in export")
    return data


def _read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows or not REQUIRED <= set(rows[0]):
        raise ValueError("not an Untappd check-in export")
    return rows


def find_export(root=ROOT):
    """Newest CSV/JSON in root that parses as an Untappd export."""
    paths = glob.glob(os.path.join(root, "*.csv")) + glob.glob(os.path.join(root, "*.json"))
    for path in sorted(paths, key=os.path.getmtime, reverse=True):
        try:
            (_read_json if path.endswith(".json") else _read_csv)(path)
            return path
        except (ValueError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise FileNotFoundError(
        "No Untappd export found. Put your .csv or .json export in the project folder.")


def _text(v):
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)


def _normalize_json_row(r):
    row = {k: _text(v) for k, v in r.items()}
    # JSON gives "2010-11-22T19:43:38-05:00"; the CSV has local time plus a UTC column.
    iso = r.get("created_at") or ""
    try:
        dt = datetime.fromisoformat(iso)
        row["created_at_iso"] = iso
        row["created_at"] = dt.strftime("%Y-%m-%d %H:%M:%S")
        row["created_at_utc"] = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        row["created_at_utc"] = row["created_at"]
    return row


def load_checkins(path=None):
    path = path or find_export()
    if path.endswith(".json"):
        rows = [_normalize_json_row(r) for r in _read_json(path)]
    else:
        rows = _read_csv(path)
    return rows, path
