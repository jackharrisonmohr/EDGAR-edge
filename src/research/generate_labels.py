#!/usr/bin/env python3
# generate_labels.py – v2.4
"""
SEC filing label generator (sample/text layout, .txt.gz objects)

Key improvements (v2.4)
=======================
* Separate SPX (^GSPC) fetch to guarantee presence or fail loudly.
* Chunked ticker fetch with logging of missing/delisted tickers.
* Drops filings for which no price data could be retrieved.
* Explicitly set yfinance auto_adjust=False to ensure `Adj Close` is returned.


Testing: 

poetry run python generate_labels.py     --start-date 2019-01-01 --end-date 2019-01-10     --workers 4 --limit 50
"""

import argparse
import gzip
import io
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time as dtime, timedelta
from typing import Any, Dict, List

import boto3
import botocore
from tqdm import tqdm

# ---------------- basic config ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s",
)
logger = logging.getLogger("labeler")

RAW_FILINGS_BUCKET = "edgar-edge-raw"
DEFAULT_BUCKET_PREFIX = "text/" # Use a default constant
SPX_TICKER = "^GSPC"
ABNORMAL_RETURN_DAYS = 3
LABEL_THRESHOLD = 0.008
HEAD_BYTES = 65_536            # 64 KiB for gzip header+SEC header

# ---------------- helpers ----------------

def load_cik_ticker_map(path: str) -> Dict[str, str]:
    import pathlib
    p = pathlib.Path(path)
    if not p.exists():
        logger.error("CIK→ticker map not found: %s", path)
        sys.exit(1)
    mapping: Dict[str, str] = {}
    with open(p, "r") as fh:
        for line in fh:
            ticker, cik = line.strip().split("\t")
            if cik.isdigit():
                mapping[str(int(cik))] = ticker.upper()
    logger.info("Loaded %d CIK→ticker mappings", len(mapping))
    return mapping

# -- S3 enumerate

def list_s3_keys(bucket: str, years: List[int], bucket_prefix: str) -> List[str]:
    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    keys: List[str] = []
    for yr in tqdm(years, desc="Listing years"):
        prefix = f"{bucket_prefix}{yr}/" # Use the passed prefix
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            keys.extend([
                obj["Key"]
                for obj in page.get("Contents", [])
                if obj["Key"].endswith(".txt.gz")
            ])
    logger.info("Discovered %d txt.gz objects", len(keys))
    return keys

# -- quick-parse routines
FILED_RE = re.compile(r'FILED\s+AS\s+OF\s+DATE:\s*(\d{8})')
ACCEPT_RE = re.compile(r'ACCEPTANCE-DATETIME>\s*(\d{14})')


def _parse_sec_header(plain: str) -> Dict[str, str] | None:
    """Return dict with filed_date (yyyymmdd) if found."""
    filed_date = None
    m = FILED_RE.search(plain)
    if m:
        filed_date = m.group(1)
    else:
        m = ACCEPT_RE.search(plain)
        if m:
            filed_date = m.group(1)[:8]
    if not filed_date:
        return None
    return {"filed_date": filed_date}


def _extract_head_fields(blob: bytes, key: str) -> Dict[str, Any] | None:
    """Decompress entire gzip blob, parse accession + dates, and extract text."""
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(blob)) as gf:
            full_text_content = gf.read().decode("utf-8", errors="ignore")
    except (OSError, EOFError) as e:
        logger.warning("Failed to decompress/decode S3 key %s: %s", key, e)
        return None

    acc_name = key.rsplit("/", 1)[-1].replace(".txt.gz", "")
    cik = acc_name.split("-")[0].lstrip("0")

    # Parse header from the beginning of the content for metadata
    # Assuming _parse_sec_header works on the initial part of the text
    sec_meta = _parse_sec_header(full_text_content[:HEAD_BYTES]) # Use HEAD_BYTES for header parsing
    if not sec_meta:
        logger.warning("Failed to parse SEC header for S3 key %s", key)
        return None

    import pandas as pd
    filed_dt = pd.to_datetime(sec_meta["filed_date"], format="%Y%m%d")

    return {
        "accession_no": acc_name,
        "cik": cik,
        "filed_at_dt": filed_dt,
        "s3_key": key,
        "text": full_text_content, # Add the full text content
    }


def fetch_metadata(bucket: str, keys: List[str], workers: int):
    import pandas as pd
    s3 = boto3.client("s3")

    def _pull(k: str):
        try:
            # Fetch the entire object, not just a byte range
            obj = s3.get_object(
                Bucket=bucket,
                Key=k,
            )
            full_content_blob = obj["Body"].read()
            return _extract_head_fields(full_content_blob, k)
        except botocore.exceptions.ClientError as e:
            logger.warning("S3 ClientError for key %s: %s", k, e)
            return None
        except Exception as e:
            logger.error("Unexpected error fetching/processing key %s: %s", k, e)
            return None

    recs: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as exe:
        for res in tqdm(exe.map(_pull, keys), total=len(keys),
                        desc="Fetching metadata"):
            if res:
                recs.append(res)
    return pd.DataFrame(recs)

# -- trading-calendar helpers

def next_trade_day(ts):
    from pandas.tseries.offsets import BDay
    return ts.normalize() + BDay(1)


def compute_join_date(ts):
    import pandas as pd
    est = ts.tz_localize("UTC").tz_convert("US/Eastern")
    after_close = est.time() >= dtime(16, 0)
    base = est.normalize() + (pd.Timedelta(days=1) if after_close else pd.Timedelta(0))
    return next_trade_day(base).tz_localize(None)

# -- price fetch helpers

def fetch_spx(start, end):
    import pandas as pd, yfinance as yf
    # always pass a list, so yf.download returns a DataFrame with MultiIndex columns
    raw = yf.download(
        [SPX_TICKER],
        start=start - timedelta(days=10),
        end=end + timedelta(days=10),
        progress=False,
        auto_adjust=False,
    )

    # raw.columns will be a MultiIndex like [ ('Adj Close','^GSPC'), ... ]
    try:
        # pull out the SPX Adj Close series
        adj = raw["Adj Close"][SPX_TICKER]
    except Exception:
        logger.error("Failed to locate SPX ’Adj Close’ in yfinance output:\n%s", raw.columns)
        sys.exit(1)

    if adj.empty:
        logger.error("SPX data is empty for %s → %s; cannot compute abnormal returns.", start, end)
        sys.exit(1)

    # build a one‐column DataFrame named "^GSPC"
    spx_df = adj.to_frame(name=SPX_TICKER)
    # drop any timezone info
    spx_df.index = pd.to_datetime(spx_df.index).tz_localize(None)
    logger.info("Fetched SPX: rows=%d  span=%s→%s", len(spx_df),
                spx_df.index.min().date(), spx_df.index.max().date())
    return spx_df

def fetch_ticker_prices(tickers, start, end, chunk=100, pause=1.0):
    import pandas as pd, yfinance as yf
    frames = []
    successful: List[str] = []
    for i in range(0, len(tickers), chunk):
        batch = tickers[i:i+chunk]
        try:
            raw = yf.download(
                " ".join(batch),
                start=start - timedelta(days=10),
                end=end + timedelta(days=10),
                progress=False,
                auto_adjust=False,
            )["Adj Close"]
        except Exception as e:
            logger.warning("yfinance batch failed %s: %s", batch, e)
            continue
        if raw.empty:
            logger.warning("No data for tickers: %s", batch)
            continue
        present = [c for c in raw.columns if c in batch]
        successful += present
        raw.index = pd.to_datetime(raw.index).tz_localize(None)
        frames.append(raw[present])
        if i + chunk < len(tickers):
            time.sleep(pause)
    if not frames:
        logger.error("No ticker prices fetched—aborting.")
        sys.exit(1)
    return pd.concat(frames, axis=1), successful


def compute_abn(prices):
    import numpy as np
    fwd = prices.shift(-ABNORMAL_RETURN_DAYS).div(prices).sub(1)
    spx = fwd[SPX_TICKER]
    return fwd.drop(columns=[SPX_TICKER]).subtract(spx, axis=0)

# ---------------- main pipeline ----------------

def generate_labels(start_date, end_date, workers, bucket, bucket_prefix,
                    limit=0, dry_run=False):
    import pandas as pd, pyarrow as pa, pyarrow.parquet as pq

    # 1. load mapping
    cik_map = load_cik_ticker_map("ticker.txt")

    # 2. list & metadata
    yrs = list(range(pd.to_datetime(start_date).year,
                     pd.to_datetime(end_date).year + 1))
    keys = list_s3_keys(bucket, yrs, bucket_prefix) # Pass bucket_prefix
    if limit:
        keys = keys[:limit]
        logger.info("LIMIT set: processing first %d objects", limit)
    meta = fetch_metadata(bucket, keys, workers)
    if meta.empty:
        logger.error("No metadata parsed—exiting.")
        return
    meta["ticker"] = meta["cik"].map(cik_map)
    meta.dropna(subset=["ticker"], inplace=True)
    meta["join_date"] = meta["filed_at_dt"].apply(compute_join_date)
    if dry_run:
        logger.info("Dry-run complete: %d filings parsed.", len(meta))
        return

    # 3. prices
    min_d = meta["join_date"].min()
    max_d = meta["join_date"].max()
    spx_df = fetch_spx(min_d, max_d)
    all_tickers = sorted(meta["ticker"].unique().tolist())
    prices_df, ok = fetch_ticker_prices(all_tickers, min_d, max_d)
    missing = set(all_tickers) - set(ok)
    if missing:
        logger.warning("Dropping %d missing tickers: %s", len(missing), list(missing)[:10])
        meta = meta[meta["ticker"].isin(ok)]
    prices = pd.concat([prices_df, spx_df], axis=1)
    if SPX_TICKER not in prices.columns:
        logger.error("^GSPC missing after final concat—aborting.")
        sys.exit(1)

    # 4. compute abnormal returns & melt into long form
    abn = compute_abn(prices)

    # stack() returns a Series with a two‐level index (date, ticker)
    # reset_index() turns those two levels into columns named level_0, level_1
    stacked = abn.stack().reset_index()

    # now explicitly assign the three column names we need:
    #   0) join_date  ← formerly level_0
    #   1) ticker     ← formerly level_1
    #   2) abn_ret    ← the value column
    stacked.columns = [
        "join_date",
        "ticker",
        f"abn_ret_{ABNORMAL_RETURN_DAYS}d",
    ]

    # rename that value column into your label column name
    abn_long = stacked

    merged = pd.merge(meta, abn_long,
                      on=["join_date","ticker"], how="left")
    lab_col = f"sentiment_label_{ABNORMAL_RETURN_DAYS}d"
    thr = LABEL_THRESHOLD
    merged[lab_col] = merged[f"abn_ret_{ABNORMAL_RETURN_DAYS}d"].apply(
        lambda x: 1 if x > thr else -1 if x < -thr else 0
    )
    # Include 'text' column in the final output
    final_columns = [
        "accession_no", "cik", "ticker", "filed_at_dt",
        f"abn_ret_{ABNORMAL_RETURN_DAYS}d", lab_col, "text" # Added "text"
    ]
    final = merged.dropna(subset=[f"abn_ret_{ABNORMAL_RETURN_DAYS}d"])[final_columns]
    
    logger.info("Label distribution:%s", final[lab_col].value_counts())
    if "text" in final.columns:
        logger.info("Average text length: %.2f characters", final["text"].str.len().mean())

    out = "edgar_labels.parquet"
    pq.write_table(pa.Table.from_pandas(final, preserve_index=False),
                   out, compression="snappy")
    logger.info("Saved %s (rows=%d)", out, len(final))

# ---------------- CLI ----------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Generate abnormal-return labels for SEC filings "
            "(sample/text layout, .txt.gz).\n\n"
            "Example test-run:\n"
            "  python generate_labels.py "
            "--start-date 2019-01-01 --end-date 2019-01-10 "
            "--workers 4 --limit 10 --dry-run"
        )
    )
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--bucket", default=RAW_FILINGS_BUCKET)
    parser.add_argument("--bucket-prefix", default=DEFAULT_BUCKET_PREFIX,
                        help=f"S3 bucket prefix for raw filings (default: {DEFAULT_BUCKET_PREFIX}).")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process only first N objects (debug).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse metadata only; skip price fetch & output.")
    args = parser.parse_args()

    logger.info("Run parameters: %s", args)
    generate_labels(
        args.start_date, args.end_date,
        args.workers, args.bucket, args.bucket_prefix, # Pass bucket_prefix
        limit=args.limit, dry_run=args.dry_run
    )
    logger.info("Done.")
