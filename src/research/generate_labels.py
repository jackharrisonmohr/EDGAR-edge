# generate_labels.py – v2.2
"""SEC filing label generator

Key improvements (v2.2)
=======================
* **Progress bars** with `tqdm` for S3 listing & metadata fetch.
* **Light‑weight metadata pull** — use `Range: bytes=0-16383` so we never stream the full 20 MB filing.
* Parse **true filing date** from the SEC header (`FILED AS OF DATE` or `ACCEPTANCE-DATETIME`) instead of `fetched_at`.
* Still defers heavy imports; CLI example unchanged.
"""

import argparse
import json
import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as dtime, timedelta
from typing import Any, Dict, List

import boto3
import botocore
from tqdm import tqdm

# ---------------- basic config ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("labeler")

RAW_FILINGS_BUCKET = "edgar-edge-raw"
SPX_TICKER = "^GSPC"
ABNORMAL_RETURN_DAYS = 3
LABEL_THRESHOLD = 0.008
HEAD_BYTES = 16_384  # bytes to read from each S3 object – enough for json header + SEC header

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

def list_s3_keys(bucket: str, years: List[int]) -> List[str]:
    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    keys: List[str] = []
    for yr in tqdm(years, desc="Listing years"):
        prefix = f"raw/{yr}/"
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            keys.extend([obj["Key"] for obj in page.get("Contents", []) if obj["Key"].endswith(".json")])
    logger.info("Discovered %d JSON objects", len(keys))
    return keys


# -- quick‑parse routines (avoid full JSON load)
ACC_RE = re.compile(r'"accession"\s*:\s*"([^"]+)"')
FETCHED_RE = re.compile(r'"fetched_at"\s*:\s*"([^"]+)"')
FILED_RE = re.compile(r'FILED AS OF DATE:\s*(\d{8})')
ACCEPT_RE = re.compile(r'ACCEPTANCE-DATETIME>(\d{14})')


def _extract_head_fields(blob: bytes, key: str) -> Dict[str, Any] | None:
    """Parse accession, fetched_at, and filing date (from SEC header) from the first HEAD_BYTES."""
    txt = blob.decode("utf-8", errors="ignore")

    acc_match = ACC_RE.search(txt)
    fetch_match = FETCHED_RE.search(txt)

    if not (acc_match and fetch_match):
        return None

    accession = acc_match.group(1)
    cik = accession.split("-")[0].lstrip("0")

    # Parse true filing date (UTC‑naive) from SEC header
    filed_date = None
    filed_m = FILED_RE.search(txt)
    if filed_m:
        filed_date = filed_m.group(1)  # yyyymmdd
    else:
        accp_m = ACCEPT_RE.search(txt)
        if accp_m:
            filed_date = accp_m.group(1)[:8]

    if not filed_date:
        return None

    import pandas as pd

    filed_dt = pd.to_datetime(filed_date, format="%Y%m%d")

    return {
        "accession_no": accession,
        "cik": cik,
        "filed_at_dt": filed_dt,
        "s3_key": key,
    }


# -- concurrent metadata fetch

def fetch_metadata(bucket: str, keys: List[str], workers: int) -> "pd.DataFrame":
    import pandas as pd

    s3 = boto3.client("s3")

    def _pull(k: str):
        try:
            obj = s3.get_object(Bucket=bucket, Key=k, Range=f"bytes=0-{HEAD_BYTES-1}")
            return _extract_head_fields(obj["Body"].read(), k)
        except botocore.exceptions.ClientError:
            return None

    recs: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as exe:
        for res in tqdm(exe.map(_pull, keys), total=len(keys), desc="Fetching metadata"):
            if res:
                recs.append(res)

    return pd.DataFrame(recs)


# -- trading‑calendar helpers

def next_trade_day(ts):
    import pandas as pd
    import pandas_market_calendars as mcal

    cal = mcal.get_calendar("XNYS")
    sched = cal.schedule(ts.normalize(), ts.normalize() + pd.Timedelta(days=5))
    days = sched.index.tz_localize(None)
    return days[0] if len(days) else ts.normalize()


def compute_join_date(ts):
    import pandas as pd

    est = ts.tz_localize("UTC").tz_convert("US/Eastern")
    after_close = est.time() >= dtime(16, 0)
    base = est.normalize() + (pd.Timedelta(days=1) if after_close else pd.Timedelta(0))
    return next_trade_day(base).tz_localize(None)


# -- price + abnormal return utils

def fetch_prices(tickers, start, end):
    import pandas as pd
    import yfinance as yf

    s = start - timedelta(days=10)
    e = end + timedelta(days=10)
    raw = yf.download(tickers, start=s, end=e, progress=False)["Adj Close"]
    if isinstance(raw, pd.Series):
        raw = raw.to_frame(name=tickers[0])
    raw.index = pd.to_datetime(raw.index).tz_localize(None)
    return raw.dropna(how="all", axis=1)


def compute_abn(prices):
    import numpy as np

    fwd = prices.shift(-ABNORMAL_RETURN_DAYS).div(prices).sub(1)
    spx = fwd[SPX_TICKER]
    return fwd.drop(columns=[SPX_TICKER]).subtract(spx, axis=0)


# ---------------- main pipeline ----------------

def generate_labels(start_date, end_date, workers, bucket):
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    # 1. map
    cik_map = load_cik_ticker_map("ticker.txt")

    # 2. S3 listing + metadata
    yrs = list(range(pd.to_datetime(start_date).year, pd.to_datetime(end_date).year + 1))
    keys = list_s3_keys(bucket, yrs)
    meta = fetch_metadata(bucket, keys, workers)
    if meta.empty:
        logger.error("No metadata parsed – exiting")
        return

    meta["ticker"] = meta["cik"].map(cik_map)
    meta.dropna(subset=["ticker"], inplace=True)
    meta["join_date"] = meta["filed_at_dt"].apply(compute_join_date)

    # 3. prices
    tickers = sorted(meta["ticker"].unique().tolist()) + [SPX_TICKER]
    prices = fetch_prices(tickers, meta["join_date"].min(), meta["join_date"].max())
    meta = meta[meta["ticker"].isin(prices.columns)]

    # 4. abnormal returns
    abn = compute_abn(prices)
    abn_long = (
        abn.stack()
        .reset_index()
        .rename(columns={0: f"abn_ret_{ABNORMAL_RETURN_DAYS}d", "level_0": "join_date", "level_1": "ticker"})
    )

    merged = pd.merge(meta, abn_long, on=["join_date", "ticker"], how="left")
    lab_col = f"sentiment_label_{ABNORMAL_RETURN_DAYS}d"
    thr = LABEL_THRESHOLD
    merged[lab_col] = merged[f"abn_ret_{ABNORMAL_RETURN_DAYS}d"].apply(
        lambda x: 1 if x > thr else -1 if x < -thr else 0
    )

    final = merged.dropna(subset=[f"abn_ret_{ABNORMAL_RETURN_DAYS}d"])[
        [
            "accession_no",
            "cik",
            "ticker",
            "filed_at_dt",
            f"abn_ret_{ABNORMAL_RETURN_DAYS}d",
            lab_col,
        ]
    ]

    logger.info("Label distribution:\n%s", final[lab_col].value_counts())

    pq.write_table(pa.Table.from_pandas(final, preserve_index=False), "edgar_labels.parquet", compression="snappy")
    logger.info("Saved parquet (rows=%d)", len(final))


# ---------------- CLI ----------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate 3‑day abnormal‑return labels for SEC filings.\n\nExample:\n  python generate_labels.py --start-date 2024-01-01 --end-date 2024-01-31 --workers 8"
    )
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--bucket", default=RAW_FILINGS_BUCKET)
    args = parser.parse_args()

    logger.info("Run parameters: %s", args)
    generate_labels(args.start_date, args.end_date, args.workers, args.bucket)
    logger.info("Done.")
