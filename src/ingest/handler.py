import boto3
import os
import feedparser
import json
import hashlib
from datetime import datetime, timezone
import urllib.request
import uuid # For batch entry IDs

S3 = boto3.client("s3")
SQS = boto3.client("sqs") # Initialize SQS client
BUCKET = os.environ["RAW_BUCKET"]
RSS = os.environ["RSS_URL"]
SCORE_QUEUE_URL = os.environ["SCORE_QUEUE_URL"] # Get SQS queue URL

def lambda_handler(event, context):
    req = urllib.request.Request(
        RSS,
        headers={"User-Agent": "EDGAR-Edge jackharrisonmohr@gmail.com"}
    )
    with urllib.request.urlopen(req) as response:
        feed = feedparser.parse(response.read())

    print(f"Bucket: {BUCKET}")
    print(f"RSS URL: {RSS}")
    print(f"Score Queue URL: {SCORE_QUEUE_URL}")
    print(f"Feed entries: {len(feed.entries)}")

    sqs_messages = []
    s3_put_count = 0
    processed_count = 0

    for e in feed.entries:
        processed_count += 1
        try:
            accession_no = e.id.split("accession-number=")[-1]
            filed_at_str = e.updated
            link = e.link

            # Calculate S3 object key
            # Using accession_no directly might be better for retrieval if unique
            # md5 = hashlib.md5(accession_no.encode()).hexdigest()
            # object_key = f"raw/{datetime.utcnow():%Y/%m/%d}/{md5}.json"
            # Let's use a simpler structure for now, assuming accession_no is unique enough path component
            # Consider potential S3 key partitioning limits if volume is massive
            filed_dt_utc = datetime.strptime(filed_at_str, "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone.utc)
            object_key = f"raw/{filed_dt_utc:%Y/%m/%d}/{accession_no}.json"

            # 1. Put object to S3
            s3_body = json.dumps({
                "accession_no": accession_no,
                "filed_at": filed_at_str,
                "link": link,
            })
            S3.put_object(
                Bucket=BUCKET,
                Key=object_key,
                Body=s3_body.encode('utf-8'),
                ContentType='application/json'
            )
            s3_put_count += 1

            # Log latency
            lag = (datetime.now(timezone.utc) - filed_dt_utc).total_seconds()
            print(f"LAG_SECS {lag:.1f} for {accession_no}")

            # 2. Prepare SQS message
            message_body = json.dumps({
                "accession_no": accession_no,
                "s3_bucket": BUCKET,
                "s3_key": object_key,
                "filed_at": filed_at_str,
            })
            sqs_messages.append({
                'Id': str(uuid.uuid4()), # Unique ID for the batch entry
                'MessageBody': message_body,
                'MessageDeduplicationId': accession_no, # Use accession number for deduplication
                'MessageGroupId': 'filings' # Required for FIFO queues
            })

        except Exception as err:
            print(f"ERROR processing entry {e.get('id', 'N/A')}: {err}")
            # Decide if you want to continue or raise/fail

    # Send messages to SQS in batches of 10
    sqs_sent_count = 0
    if sqs_messages:
        for i in range(0, len(sqs_messages), 10):
            batch = sqs_messages[i:i + 10]
            try:
                response = SQS.send_message_batch(
                    QueueUrl=SCORE_QUEUE_URL,
                    Entries=batch
                )
                sqs_sent_count += len(batch)
                if response.get('Failed'):
                    print(f"ERROR SQS SendMessageBatch failed for some messages: {response['Failed']}")
            except Exception as err:
                print(f"ERROR sending SQS batch: {err}")
                # Handle partial batch failure or retry logic if needed

    print(f"Processed: {processed_count}, S3 Puts: {s3_put_count}, SQS Messages Sent: {sqs_sent_count}")
    return {"status": "ok", "processed": processed_count, "s3_puts": s3_put_count, "sqs_sent": sqs_sent_count}
