"""
Asynchronous back-fill of SEC 8-K / 10-K filings — single event loop.

Usage:
    python -m src.ingest.async_backfill --mode s3 --bucket <bucket> --years 2020 2021 …
"""

import asyncio
import gzip
import functools # Import functools
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
    "User-Agent": "EDGAR-Edge2 jackharrisonmohr@gmail.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov",
}
INDEX_BASE = "https://www.sec.gov/Archives/edgar/full-index"
RATE = 10  # max requests/sec per SEC fair-access rules
SEM = asyncio.Semaphore(RATE)

s3 = boto3.client("s3")


async def fetch(session: aiohttp.ClientSession, url: str) -> bytes:
    print(f"      -> Attempting fetch: {url}") # DEBUG
    async with SEM:
        print(f"      -> Acquired semaphore for: {url}") # DEBUG
        try:
            # Rely on session timeouts configured below
            async with session.get(url) as resp:
                print(f"      -> Got response status {resp.status} for: {url}") # DEBUG
                resp.raise_for_status()
                print(f"      -> Reading response for: {url}") # DEBUG
                content = await resp.read()
                print(f"      -> Finished reading response for: {url}") # DEBUG
                return content
        except asyncio.TimeoutError:
            print(f"    ! Timeout error fetching {url}")
            raise # Re-raise to be handled upstream or logged
        except aiohttp.ClientError as e:
            print(f"    ! Client error fetching {url}: {e}")
            raise # Re-raise
        finally:
            print(f"      -> Released semaphore for: {url}") # DEBUG


async def save_filing(
    session: aiohttp.ClientSession,
    year: int,
    accession: str,
    url: str,
    mode: str,
    bucket: Optional[str],
):
    loop = asyncio.get_running_loop()
    key = f"raw/{year}/{accession}.json"

    if mode == "s3":
        try:
            # Use functools.partial to pass keyword arguments to head_object via executor
            head_object_partial = functools.partial(s3.head_object, Bucket=bucket, Key=key)
            await loop.run_in_executor(None, head_object_partial)
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
        try:
            # Use functools.partial to pass keyword arguments to put_object via executor
            put_object_partial = functools.partial(s3.put_object, Bucket=bucket, Key=key, Body=body)
            await loop.run_in_executor(None, put_object_partial)
            print(f"    ✓ Uploaded s3://{bucket}/{key}")
        except Exception as e:
             print(f"    ! S3 Error uploading key: s3://{bucket}/{key}. Error: {e}")
             # Decide if we should return or raise here depending on desired behavior
             return # For now, log error and skip this filing on upload failure
    else:
        # Local file writing is also blocking, run in executor too for consistency
        path = os.path.join("data", "raw", str(year), f"{accession}.json")
        try:
            # Define a helper function for the blocking file operations
            def write_local_file():
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(body)

            await loop.run_in_executor(None, write_local_file)
            print(f"    ✓ Saved {path}")
        except Exception as e:
            print(f"    ! Error saving local file: {path}. Error: {e}")
            return # Log error and skip


async def one_quarter(
    session: aiohttp.ClientSession,
    year: int,
    quarter: int,
    mode: str,
    bucket: Optional[str],
    batch_size: int = 1000  # Process filings in batches
):
    idx_url = f"{INDEX_BASE}/{year}/QTR{quarter}/master.idx"
    print(f"  • Fetching index {idx_url}")
    try:
        raw = await fetch(session, idx_url)
    except Exception as e:
        print(f"    ! Failed to fetch index {idx_url}: {e}")
        return # Skip this quarter if index fetch fails

    print(f"    -- Processing index {idx_url}...")
    tasks = []
    processed_count = 0
    filing_count = 0
    header_found = False

    # Process the index file line by line to save memory
    try:
        with io.TextIOWrapper(io.BytesIO(raw), encoding='utf-8', errors='ignore') as f:
            for line in f:
                if not header_found:
                    if line.startswith("CIK|"):
                        header_found = True
                    continue # Skip lines until header row

                parts = line.strip().split("|")
                if len(parts) < 5:
                    continue
                _, _, form, _, filename = parts
                if form not in ("8-K", "10-K"):
                    continue

                filing_count += 1
                accession = os.path.basename(filename).replace(".txt", "")
                filing_url = "https://www.sec.gov/Archives/" + filename
                tasks.append(save_filing(session, year, accession, filing_url, mode, bucket))

                # If batch is full, run tasks and reset
                if len(tasks) >= batch_size:
                    print(f"      > Gathering batch of {len(tasks)} filing tasks...")
                    await asyncio.gather(*tasks)
                    processed_count += len(tasks)
                    print(f"      > Batch complete. Total processed so far: {processed_count}")
                    tasks = [] # Reset tasks list for next batch

            # Process any remaining tasks in the last batch
            if tasks:
                print(f"      > Gathering final batch of {len(tasks)} filing tasks...")
                await asyncio.gather(*tasks)
                processed_count += len(tasks)
                print(f"      > Final batch complete.")

        if not header_found:
             print("    ! No header line found in index file.")

        print(f"    -- Finished processing index {idx_url}. Found {filing_count} relevant filings. Processed {processed_count} tasks.")

    except Exception as e:
        print(f"    ! Error processing index file {idx_url}: {e}")
        # If tasks were pending, try to gather them anyway? Or just log error.
        # For simplicity, just log and move on. Potential partial processing.
        if tasks:
             print(f"    ! {len(tasks)} tasks were pending when error occurred.")


async def run(years: List[int], mode: str, bucket: Optional[str]):
    # Set up one session *inside* this loop
    # Configure more specific timeouts
    timeout = aiohttp.ClientTimeout(
        total=None,        # No overall total time limit for the session
        connect=30,        # Max 30 seconds to establish connection
        sock_connect=30,   # Max 30 seconds for socket connection attempt
        sock_read=60       # Max 60 seconds to read data from socket
    )
    connector = aiohttp.TCPConnector(limit_per_host=RATE, limit=None)
    async with aiohttp.ClientSession(
        headers=SEC_HEADERS, connector=connector, timeout=timeout
    ) as session:
        for year in years:
            print(f"\nProcessing Year: {year}")
            for q in range(1, 5):
                print(f"  Processing Quarter: Q{q}")
                await one_quarter(session, year, q, mode, bucket) # batch_size defaults to 1000
                # small pause to keep the SEC happy across quarters
                print(f"  -- Quarter Q{q} finished, pausing...")
                time.sleep(0.5)
            print(f"Finished Year: {year}")


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
