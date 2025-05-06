import asyncio
import gzip
import io
import json
import os
from datetime import datetime
from typing import List, Optional

import aiohttp
import boto3
import botocore

'''
# This script is designed to backfill SEC filings from the EDGAR database.
# ──────────────────────────────────────────────────────────────────────────


This is how I set up the EC2 instance to run the async backfill script.

aws ec2 run-instances \
  --image-id ami-0f88e80871fd81e91 \
  --instance-type t3.small \
  --count 1 \
  --key-name harrison2025 \
  --iam-instance-profile Name=edgar-edge-backfill-ec2-profile \
  --instance-market-options '{"MarketType":"spot"}'

  
```bash
#!/bin/bash
sudo yum update -y
sudo yum install git -y
git clone --branch sprint2 https://github.com/jackharrisonmohr/EDGAR-edge.git
cd EDGAR-Edge
python3 -m venv venv
source venv/bin/activate
pip install aiohttp boto3
python3 -m src.ingest.async_backfill --mode s3 --bucket edgar-edge-raw --years 2019 2020 2021 2022 2023 2024
```
# ──────────────────────────────────────────────────────────────────────────

'''

# ──────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────
RATE = 5  # Max requests per second

# SEC polite-access headers (ASCII only)
SEC_HEADERS = {
    "User-Agent": "EDGAR-Edge2 jackharrisonmohr@gmail.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov",
}
INDEX_BASE = "https://www.sec.gov/Archives/edgar/full-index"


async def fetch(
    session: aiohttp.ClientSession,
    url: str,
    sem: asyncio.Semaphore,
) -> bytes:
    """
    Fetch content from the given URL, respecting the semaphore rate limit.
    """
    async with sem:
        try:
            async with session.get(url) as resp:
                resp.raise_for_status()
                return await resp.read()
        except asyncio.TimeoutError:
            print(f"    ! Timeout error fetching {url}")
            raise
        except aiohttp.ClientError as e:
            print(f"    ! Client error fetching {url}: {e}")
            raise


async def save_filing(
    session: aiohttp.ClientSession,
    year: int,
    accession: str,
    url: str,
    mode: str,
    bucket: Optional[str],
    s3_client,
    sem: asyncio.Semaphore,
):
    """
    Download and save a single filing (to S3 or local filesystem).
    """
    key = f"raw/{year}/{accession}.json"

    if mode == "s3":
        try:
            s3_client.head_object(Bucket=bucket, Key=key)
            print(f"    ○ Skipping {accession}, already in s3://{bucket}/{key}")
            return
        except botocore.exceptions.ClientError as e:
            if e.response.get("Error", {}).get("Code") != "404":
                raise

    try:
        data = await fetch(session, url, sem)
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

    if mode == "s3":
        try:
            s3_client.put_object(Bucket=bucket, Key=key, Body=body)
            print(f"    ✓ Uploaded s3://{bucket}/{key}")
        except Exception as e:
            print(f"    ! S3 Error uploading key s3://{bucket}/{key}: {e}")
            return
    else:
        path = os.path.join("data", "raw", str(year), f"{accession}.json")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(body)
            print(f"    ✓ Saved {path}")
        except Exception as e:
            print(f"    ! Error saving local file {path}: {e}")


async def one_quarter(
    session: aiohttp.ClientSession,
    year: int,
    quarter: int,
    mode: str,
    bucket: Optional[str],
    s3_client,
    sem: asyncio.Semaphore,
    batch_size: int = 100,
):
    """
    Process all filings for a single quarter.
    """
    idx_url = f"{INDEX_BASE}/{year}/QTR{quarter}/master.idx"
    print(f"  • Fetching index {idx_url}")
    try:
        raw = await fetch(session, idx_url, sem)
    except Exception as e:
        print(f"    ! Failed to fetch index {idx_url}: {e}")
        return

    print(f"    -- Processing index {idx_url}...")
    tasks = []
    processed_count = 0
    filing_count = 0
    header_found = False

    try:
        with io.TextIOWrapper(io.BytesIO(raw), encoding='utf-8', errors='ignore') as f:
            for line in f:
                if not header_found:
                    if line.startswith("CIK|"):
                        header_found = True
                    continue

                parts = line.strip().split("|")
                if len(parts) < 5:
                    continue
                _, _, form, _, filename = parts
                if form not in ("8-K", "10-K"):
                    continue

                filing_count += 1
                accession = os.path.basename(filename).replace(".txt", "")
                filing_url = "https://www.sec.gov/Archives/" + filename
                tasks.append(
                    save_filing(
                        session, year, accession, filing_url,
                        mode, bucket, s3_client, sem
                    )
                )

                if len(tasks) >= batch_size:
                    print(f"      > Gathering batch of {len(tasks)} filing tasks...")
                    await asyncio.gather(*tasks)
                    processed_count += len(tasks)
                    print(f"      > Batch complete. Total processed so far: {processed_count}")
                    tasks = []

            if tasks:
                print(f"      > Gathering final batch of {len(tasks)} filing tasks...")
                await asyncio.gather(*tasks)
                processed_count += len(tasks)
                print("      > Final batch complete.")

        if not header_found:
            print("    ! No header line found in index file.")

        print(
            f"    -- Finished processing index {idx_url}. "
            f"Found {filing_count} relevant filings, processed {processed_count} tasks."
        )

    except Exception as e:
        print(f"    ! Error processing index file {idx_url}: {e}")
        if tasks:
            print(f"    ! {len(tasks)} tasks were pending when error occurred.")


async def run(years: List[int], mode: str, bucket: Optional[str]):
    """
    Orchestrates the backfill over multiple years.
    """
    timeout = aiohttp.ClientTimeout(
        total=None,
        connect=30,
        sock_connect=30,
        sock_read=60,
    )
    connector = aiohttp.TCPConnector(limit_per_host=RATE, limit=None)

    # Create semaphore inside the event loop
    sem = asyncio.Semaphore(RATE)
    s3_client = boto3.client("s3")

    async with aiohttp.ClientSession(
        headers=SEC_HEADERS,
        connector=connector,
        timeout=timeout
    ) as session:
        for year in years:
            print(f"\nProcessing Year: {year}")
            for q in range(1, 5):
                print(f"  Processing Quarter: Q{q}")
                await one_quarter(
                    session, year, q, mode, bucket, s3_client, sem
                )
                print(f"  -- Quarter Q{q} finished, pausing...")
                await asyncio.sleep(0.5)
            print(f"Finished Year: {year}")


def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Asynchronous back-fill of SEC filings"
    )
    parser.add_argument(
        "--mode", choices=["local", "s3"], required=True,
        help="Save mode: 'local' or 's3'"
    )
    parser.add_argument(
        "--bucket", help="S3 bucket (required if mode is s3)"
    )
    parser.add_argument(
        "--years", type=int, nargs='+', required=True,
        help="List of years to backfill, e.g. 2020 2021"
    )
    args = parser.parse_args()

    if args.mode == "s3" and not args.bucket:
        sys.exit("Error: --bucket is required when mode is s3")

    asyncio.run(run(args.years, args.mode, args.bucket))


if __name__ == "__main__":
    main()
