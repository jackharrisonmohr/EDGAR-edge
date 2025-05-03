"""
Download or back‑fill SEC 8‑K / 10‑K filings.

  • mode="local" –> ./data/raw/{year}/{accession}.json
  • mode="s3"    –> s3://{bucket}/raw/{year}/{accession}.json

  entries in the idx files look like this:

CIK|Company Name|Form Type|Date Filed|Filename
--------------------------------------------------------------------------------
1000045|NICHOLAS FINANCIAL INC|10-Q|2024-02-13|edgar/data/1000045/0000950170-24-014566.txt
1000045|NICHOLAS FINANCIAL INC|424B3|2024-03-19|edgar/data/1000045/0000950170-24-033226.txt
1000045|NICHOLAS FINANCIAL INC|8-K|2024-02-13|edgar/data/1000045/0000950170-24-014524.txt
1000045|NICHOLAS FINANCIAL INC|8-K|2024-02-14|edgar/data/1000045/0000950170-24-015038.txt
1000045|NICHOLAS FINANCIAL INC|8-K|2024-03-04|edgar/data/1000045/0000950170-24-024439.txt
1000045|NICHOLAS FINANCIAL INC|CORRESP|2024-01-10|edgar/data/1000045/0000950170-24-003550.txt
...
"""

import gzip
import io
import json
import os
import time
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter, Retry

try:
    import boto3  # only needed for S3 uploads
except ImportError:
    boto3 = None  # type: ignore[assignment]

# ──────────────────────────────────────────────────────────────────────────
#   SEC polite‑access headers  (must be ASCII; see fair‑access rules)
# ──────────────────────────────────────────────────────────────────────────
USER_AGENT = "EDGAR-Edge harrisonmohr@gmail.com"
SEC_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov",
}

# Root for quarterly master files
INDEX_BASE = "https://www.sec.gov/Archives/edgar/full-index"

# ──────────────────────────────────────────────────────────────────────────
#   shared HTTP session with retries + back‑off
# ──────────────────────────────────────────────────────────────────────────
_session = requests.Session()
_session.headers.update(SEC_HEADERS)
_session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=5,
            backoff_factor=1.0,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"],
        )
    ),
)

RATE_DELAY = 0.12  # keep <10 requests/sec


# ──────────────────────────────────────────────────────────────────────────
#   public entry point
# ──────────────────────────────────────────────────────────────────────────
def download_filings(year: int, mode: str, bucket: str | None = None) -> None:
    if mode == "s3" and not bucket:
        raise ValueError("bucket must be provided when mode == 's3'")

    for q in range(1, 5):
        idx_url = f"{INDEX_BASE}/{year}/QTR{q}/master.gz"
        print(f"  • Fetching index {idx_url}")
        resp = _session.get(idx_url, timeout=30)
        resp.raise_for_status()

        # decompress and split into lines
        with gzip.GzipFile(fileobj=io.BytesIO(resp.content)) as gz:
            text = gz.read().decode("utf-8", errors="ignore")
        lines = text.splitlines()

        try:
            start = next(i for i, ln in enumerate(lines) if ln.startswith("CIK|")) + 1
        except StopIteration:
            print("    ! Could not find header line in index – skipping quarter")
            continue

        for line in lines[start:]:
            parts = line.split("|")
            if len(parts) < 5:
                continue
            cik, comp, form, date_str, filename = parts
            if form not in ("8-K", "10-K"):
                continue

            accession = os.path.basename(filename).replace(".txt", "")
            filing_url = "https://www.sec.gov/Archives/" + filename
            _save_filing(year, accession, filing_url, mode, bucket)
            time.sleep(RATE_DELAY)


# ──────────────────────────────────────────────────────────────────────────
#   helpers
# ──────────────────────────────────────────────────────────────────────────
def _save_filing(
    year: int,
    accession: str,
    url: str,
    mode: str,
    bucket: str | None,
) -> None:
    try:
        resp = _session.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as exc:
        print(f"    ! Error fetching {accession}: {exc}")
        return

    record = {
        "accession": accession,
        "fetched_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "url": url,
        "content": resp.text,
    }
    body = json.dumps(record).encode()

    if mode == "local":
        path = os.path.join("data", "raw", str(year), f"{accession}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(body)
        print(f"    ✓ Saved {path}")

    else:  # mode == "s3"
        if boto3 is None:
            raise RuntimeError("boto3 is required for S3 uploads")
        key = f"raw/{year}/{accession}.json"
        boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=body)
        print(f"    ✓ Uploaded s3://{bucket}/{key}")
