import boto3, os, feedparser, json, hashlib
from datetime import datetime, timezone
import urllib.request

S3 = boto3.client("s3")
BUCKET = os.environ["RAW_BUCKET"]
RSS = os.environ["RSS_URL"]

def lambda_handler(event, context):
    req = urllib.request.Request(
        RSS,
        headers={"User-Agent": "EDGAR-Edge jackharrisonmohr@gmail.com"}
    )
    with urllib.request.urlopen(req) as response:
        feed = feedparser.parse(response.read())

    print('bucket: ', BUCKET)
    print('rss: ', RSS)
    print('feed entries:', len(feed.entries))

    for e in feed.entries:
        key = e.id.split("accession-number=")[-1]
        md5 = hashlib.md5(key.encode()).hexdigest()
        object_key = f"raw/{datetime.utcnow():%Y/%m/%d}/{md5}.json"
        S3.put_object(
            Bucket=BUCKET,
            Key=object_key,
            Body=json.dumps({
                "accession_no": key,
                "filed_at": e.updated,
                "link": e.link,
            }).encode(),
        )
        filed = datetime.strptime(e.updated, "%Y-%m-%dT%H:%M:%S%z")
        lag = (datetime.now(timezone.utc) - filed).total_seconds()
        print(f"LAG_SECS {lag:.1f}")
    return {"status": "ok", "count": len(feed.entries)}
