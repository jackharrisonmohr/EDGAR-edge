# src/ingest/async_backfill.py
import asyncio, aiohttp, gzip, io, json, os, time
from datetime import datetime
import boto3

SEC_HEADERS = {
    "User-Agent": "EDGAR-Edge harrisonmohr@gmail.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov",
}
INDEX_BASE = "https://www.sec.gov/Archives/edgar/full-index"
RATE = 10                    # SEC max rps
SEM   = asyncio.Semaphore(RATE)

session: aiohttp.ClientSession | None = None
s3 = boto3.client("s3")

async def fetch(url: str) -> bytes:
    async with SEM:
        async with session.get(url, timeout=30) as r:
            r.raise_for_status()
            return await r.read()

async def save_filing(year, accession, url, mode, bucket):
    try:
        text = (await fetch(url)).decode("utf8", "ignore")
    except Exception as exc:
        print("!", accession, exc)
        return
    key = f"raw/{year}/{accession}.json"
    body = json.dumps({
        "accession": accession,
        "fetched_at": datetime.utcnow().isoformat(timespec="seconds")+"Z",
        "url": url,
        "content": text,
    }).encode()
    if mode == "s3":
        s3.put_object(Bucket=bucket, Key=key, Body=body)
    else:
        path = f"data/raw/{year}/{accession}.json"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path,"wb").write(body)

async def one_quarter(year, q, mode, bucket):
    idx_url = f"{INDEX_BASE}/{year}/QTR{q}/master.gz"
    print("index", idx_url)
    data = await fetch(idx_url)
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
        lines = gz.read().decode().splitlines()
    start = next(i for i,l in enumerate(lines) if l.startswith("CIK|"))+1
    tasks=[]
    for ln in lines[start:]:
        *_, form, _, filename = ln.split("|",4)
        if form not in ("8-K","10-K"): continue
        acc = os.path.basename(filename).replace(".txt","")
        url = "https://www.sec.gov/Archives/"+filename
        tasks.append(asyncio.create_task(save_filing(year, acc, url, mode, bucket)))
    await asyncio.gather(*tasks)

async def run(years, mode, bucket):
    global session
    timeout = aiohttp.ClientTimeout(total=None)
    conn    = aiohttp.TCPConnector(limit=None, limit_per_host=RATE)
    async with aiohttp.ClientSession(headers=SEC_HEADERS, connector=conn,
                                     timeout=timeout) as session:
        for y in years:
            for q in range(1,5):
                await one_quarter(y,q,mode,bucket)

if __name__ == "__main__":
    import argparse, sys
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["local","s3"], required=True)
    p.add_argument("--bucket")
    p.add_argument("--years", nargs="+", type=int, required=True)
    args=p.parse_args()
    if args.mode=="s3" and not args.bucket:
        sys.exit("--bucket required with --mode s3")
    asyncio.run(run(args.years, args.mode, args.bucket))
