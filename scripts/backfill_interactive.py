#!/usr/bin/env python3
import sys
import os
import argparse

'''
# Allow imports from src/ingest

Usage:
# Local download:
python scripts/backfill.py --mode local --years 2019 2020

# Upload directly to S3:
python scripts/backfill.py --mode s3 --years 2019 2020 --bucket my-edgar-raw-bucket
'''
ROOT = os.path.abspath(os.path.join(__file__, os.pardir, os.pardir))
sys.path.insert(0, os.path.join(ROOT, "src"))

from ingest.backfill import download_filings

def main():
    p = argparse.ArgumentParser(
        description="Download SEC filings locally or to S3 (2019–2024)."
    )
    p.add_argument(
        "--mode", choices=["local", "s3"], required=True,
        help="local: save under ./data/raw; s3: upload to S3"
    )
    p.add_argument(
        "--years", nargs="+", type=int, default=list(range(2019, 2025)),
        help="Space-separated years to backfill (default: 2019 2020 … 2024)"
    )
    p.add_argument(
        "--bucket", help="S3 bucket name (required for s3 mode)"
    )
    args = p.parse_args()

    if args.mode == "s3" and not args.bucket:
        p.error("--bucket is required in s3 mode")

    for year in args.years:
        print(f"\n▶ Backfilling {year} → mode={args.mode}")
        download_filings(year, mode=args.mode, bucket=args.bucket)

if __name__ == "__main__":
    main()
