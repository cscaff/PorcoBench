#!/usr/bin/env python3
"""Fetch and verify the benchmark CNF corpus listed in a manifest.

The CNF files are not stored in this repository: not every instance is
cleared for redistribution (see the `license_status` column of
manifest.csv). Each manifest row pins the upstream URL (Global Benchmark
Database, benchmark-database.de) and the exact bytes:

  compressed_bytes / compressed_sha256  of the downloaded .cnf.xz
  cnf_sha256                            of the decompressed DIMACS text

A file is accepted only if all three match; anything else is an error and is
never written to cnf/. Re-running is safe: verified files are skipped.

Usage (from the repository root):
  python3 scripts/fetch_corpus.py                     # all 210 instances
  python3 scripts/fetch_corpus.py --manifest manifest.fit-uncertified20.csv
  python3 scripts/fetch_corpus.py --verify-only       # check local files only
  python3 scripts/fetch_corpus.py --jobs 8

Exit code 0 = every listed instance present and verified; 1 = otherwise.
Standard library only.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import hashlib
import lzma
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_AGENT = "porcobench-fetch/1"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_bytes(row: dict, raw: bytes) -> str | None:
    """None if `raw` is exactly the manifest's file, else the reason."""
    if len(raw) != int(row["compressed_bytes"]):
        return (f"size {len(raw)} != manifest {row['compressed_bytes']}")
    if sha256(raw) != row["compressed_sha256"]:
        return "compressed sha256 mismatch"
    try:
        text = lzma.decompress(raw)
    except lzma.LZMAError as e:
        return f"xz decompression failed: {e}"
    if sha256(text) != row["cnf_sha256"]:
        return "decompressed (cnf) sha256 mismatch"
    return None


def download(url: str, timeout: int, tries: int) -> bytes:
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            err = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"download failed after {tries} tries: {err}")


def handle(row: dict, base: str, verify_only: bool, timeout: int,
           tries: int) -> tuple[str, str, str | None]:
    """Returns (id, state, error) with state in present|fetched|failed."""
    dest = os.path.join(base, row["file"])
    if os.path.isfile(dest):
        with open(dest, "rb") as f:
            err = check_bytes(row, f.read())
        if err is None:
            return row["id"], "present", None
        if verify_only:
            return row["id"], "failed", f"local file invalid: {err}"
    elif verify_only:
        return row["id"], "failed", "missing"
    try:
        raw = download(row["url"], timeout, tries)
    except RuntimeError as e:
        return row["id"], "failed", str(e)
    err = check_bytes(row, raw)
    if err:
        return row["id"], "failed", f"downloaded bytes rejected: {err}"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, dest)
    return row["id"], "fetched", None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=os.path.join(ROOT, "manifest.csv"))
    ap.add_argument("--verify-only", action="store_true",
                    help="do not download; verify the files already in cnf/")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--tries", type=int, default=3)
    args = ap.parse_args()

    manifest = os.path.abspath(args.manifest)
    base = os.path.dirname(manifest)      # manifest `file` paths are relative
    with open(manifest, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print(f"error: {manifest} has no rows", file=sys.stderr)
        return 1

    states: Counter = Counter()
    failures = []
    with cf.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        futs = [ex.submit(handle, r, base, args.verify_only, args.timeout,
                          args.tries) for r in rows]
        for n, fut in enumerate(cf.as_completed(futs), 1):
            iid, state, err = fut.result()
            states[state] += 1
            if err:
                failures.append((iid, err))
            if state != "present" or n == len(rows):
                print(f"[{n}/{len(rows)}] {iid}: {state}"
                      + (f" ({err})" if err else ""), flush=True)

    print(f"\nverified present: {states['present'] + states['fetched']}"
          f"/{len(rows)} (fetched now: {states['fetched']}, "
          f"failed: {states['failed']})")
    lic = Counter(r.get("license_status", "") for r in rows)
    print("license status of these instances (see manifest.csv):")
    for k, v in lic.most_common():
        print(f"  {v:4d}  {k}")
    if failures:
        print("\nfailures:", file=sys.stderr)
        for iid, err in sorted(failures):
            print(f"  {iid}: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
