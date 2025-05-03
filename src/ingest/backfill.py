import os
import gzip
import io
import json
import requests
from datetime import datetime

try:
    import boto3
except ImportError:
    boto3 = None  # only needed in S3 mode

def download_filings(year: int, mode: str, bucket: str = None):
    """
    Downloads all 8-K and 10-K filings for `year`.
    mode="local" → writes to ./data/raw/{year}/{accession}.json
    mode="s3"    → uploads to s3://{bucket}/raw/{year}/{accession}.json
    """
    for q in range(1, 5):
        idx_url = (
            f"https://www.sec.gov/Archives/edgar/daily-index/"
            f"{year}/QTR{q}/master.gz"
        )
        print(f"  • Fetching index {idx_url}")
        resp = requests.get(idx_url)
        resp.raise_for_status()

        # decompress and split lines
        with gzip.GzipFile(fileobj=io.BytesIO(resp.content)) as gz:
            text = gz.read().decode("utf-8", errors="ignore")
        lines = text.splitlines()

        # find where the table starts (after header)
        start = 0
        for i, line in enumerate(lines):
            if line.startswith("CIK|"):
                start = i + 1
                break

        # iterate filings
        for line in lines[start:]:
            parts = line.split("|")
            if len(parts) < 5:
                continue
            cik, comp, form, date_str, filename = parts
            if form not in ("8-K", "10-K"):
                continue

            # derive accession and URL
            accession = os.path.basename(filename).replace(".txt", "")
            filing_url = "https://www.sec.gov/Archives/" + filename

            _save_filing(year, accession, filing_url, mode, bucket)


def _save_filing(year: int, accession: str, url: str, mode: str, bucket: str):
    """Fetches a single filing and writes JSON to local or S3."""
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        content = resp.text
    except Exception as e:
        print(f"    ! Error fetching {accession} at {url}: {e}")
        return

    record = {
        "accession": accession,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "url": url,
        "content": content,
    }
    body = json.dumps(record).encode("utf-8")

    if mode == "local":
        path = os.path.join("data", "raw", str(year), f"{accession}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(body)
        print(f"    ✓ Saved local {path}")

    else:  # mode == "s3"
        if boto3 is None:
            raise RuntimeError("boto3 required for s3 mode")
        s3 = boto3.client("s3")
        key = f"raw/{year}/{accession}.json"
        s3.put_object(Bucket=bucket, Key=key, Body=body)
        print(f"    ✓ Uploaded s3://{bucket}/{key}")
