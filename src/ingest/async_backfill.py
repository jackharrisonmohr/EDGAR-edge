"""
Asynchronous back-fill of SEC 8-K / 10-K filings — single event loop.

Usage:
    python -m src.ingest.async_backfill --mode s3 --bucket <bucket> --years 2020 2021 …
"""

import asyncio
import gzip
import io
import json
import os
import time
from datetime import datetime
from typing import List, Optional

import aiohttp
import boto3
import botocore

# ──────────────────────────────────────────────────────────────────────────
# SEC polite-access headers (ASCII only)
# ──────────────────────────────────────────────────────────────────────────
SEC_HEADERS = {
    "User-Agent": "EDGAR-Edge harrisonmohr@gmail.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov",
}
INDEX_BASE = "https://www.sec.gov/Archives/edgar/full-index"
RATE = 10  # max requests/sec per SEC fair-access rules
SEM = asyncio.Semaphore(RATE)

s3 = boto3.client("s3")


async def fetch(session: aiohttp.ClientSession, url: str) -> bytes:
    async with SEM:
        async with session.get(url, timeout=30) as resp:
            resp.raise_for_status()
            return await resp.read()


async def save_filing(
    session: aiohttp.ClientSession,
    year: int,
    accession: str,
    url: str,
    mode: str,
    bucket: Optional[str],
):
    key = f"raw/{year}/{accession}.json"
    if mode == "s3":
        try:
            s3.head_object(Bucket=bucket, Key=key)
            print(f"    ○ Skipping {accession}, already in s3://{bucket}/{key}")
            return
        except botocore.exceptions.ClientError as e:
            # 404 Not Found → fall through and download
            if e.response["Error"]["Code"] != "404":
                raise
    try:
        data = await fetch(session, url)
        content = data.decode("utf-8", "ignore")
    except Exception as e:
        print(f"    ! Error fetching {accession}: {e}")
        return

    record = {
        "accession": accession,
        "fetched_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "url": url,
        "content": content,
    }
    body = json.dumps(record).encode()

    key = f"raw/{year}/{accession}.json"
    if mode == "s3":
        s3.put_object(Bucket=bucket, Key=key, Body=body)
        print(f"    ✓ Uploaded s3://{bucket}/{key}")
    else:
        path = os.path.join("data", "raw", str(year), f"{accession}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(body)
        print(f"    ✓ Saved {path}")


async def one_quarter(
    session: aiohttp.ClientSession,
    year: int,
    quarter: int,
    mode: str,
    bucket: Optional[str],
):
    idx_url = f"{INDEX_BASE}/{year}/QTR{quarter}/master.gz"
    print(f"  • Fetching index {idx_url}")
    data = await fetch(session, idx_url)

    with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
        lines = gz.read().decode("utf-8", "ignore").splitlines()

    # locate header
    try:
        start = next(i for i, ln in enumerate(lines) if ln.startswith("CIK|")) + 1
    except StopIteration:
        print("    ! No header found, skipping")
        return

    # collect coroutines (not tasks)
    coros: List[asyncio.Future] = []
    for ln in lines[start:]:
        parts = ln.split("|")
        if len(parts) < 5:
            continue
        _, _, form, _, filename = parts
        if form not in ("8-K", "10-K"):
            continue

        accession = os.path.basename(filename).replace(".txt", "")
        filing_url = "https://www.sec.gov/Archives/" + filename
        coros.append(save_filing(session, year, accession, filing_url, mode, bucket))

    # run them all under the same loop
    await asyncio.gather(*coros)


async def run(years: List[int], mode: str, bucket: Optional[str]):
    # Set up one session *inside* this loop
    timeout = aiohttp.ClientTimeout(total=None)
    connector = aiohttp.TCPConnector(limit_per_host=RATE, limit=None)
    async with aiohttp.ClientSession(
        headers=SEC_HEADERS, connector=connector, timeout=timeout
    ) as session:
        for year in years:
            for q in range(1, 5):
                await one_quarter(session, year, q, mode, bucket)
                # small pause to keep the SEC happy across quarters
                time.sleep(0.5)


def main():
    import argparse
    import sys

    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["local", "s3"], required=True)
    p.add_argument("--bucket", help="S3 bucket (required if mode is s3)")
    p.add_argument("--years", type=int, nargs="+", required=True)
    args = p.parse_args()

    if args.mode == "s3" and not args.bucket:
        sys.exit("Error: --bucket is required when mode is s3")

    asyncio.run(run(args.years, args.mode, args.bucket))


if __name__ == "__main__":
    main()
