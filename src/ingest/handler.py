import boto3
import os
import feedparser
import json
import hashlib
from datetime import datetime, timezone
import urllib.request
import uuid # For batch entry IDs
import time # For TTL calculation
from botocore.exceptions import ClientError # For conditional check exception

S3 = boto3.client("s3")
SQS = boto3.client("sqs")
DYNAMODB = boto3.resource("dynamodb") # Initialize DynamoDB resource
BUCKET = os.environ["RAW_BUCKET"]
RSS = os.environ["RSS_URL"]
SCORE_QUEUE_URL = os.environ["SCORE_QUEUE_URL"]
DEDUPE_TABLE_NAME = os.environ["DEDUPE_TABLE"] # Get DynamoDB table name
DEDUPE_TABLE = DYNAMODB.Table(DEDUPE_TABLE_NAME)
TTL_SECONDS = 7 * 24 * 60 * 60 # 7 days for TTL

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
    skipped_count = 0 # Add counter for skipped items
    sqs_prepared_count = 0 # Counter for messages prepared for SQS

    for e in feed.entries:
        processed_count += 1
        accession_no = None # Initialize in case of early error
        try:
            accession_no = e.id.split("accession-number=")[-1]
            filed_at_str = e.updated
            link = e.link

            # 1. Attempt to write to DynamoDB with condition to prevent duplicates
            current_time_epoch = int(time.time())
            ttl_value = current_time_epoch + TTL_SECONDS
            try:
                DEDUPE_TABLE.put_item(
                    Item={
                        'accession_no': accession_no,
                        'processed_at': current_time_epoch,
                        'ttl': ttl_value # Add TTL attribute
                    },
                    ConditionExpression='attribute_not_exists(accession_no)'
                )
                # If successful (no exception), proceed to S3 and SQS
                print(f"Processing new filing: {accession_no}")

            except ClientError as ce:
                # Handle conditional check failure (item already exists)
                if ce.response['Error']['Code'] == 'ConditionalCheckFailedException':
                    print(f"Skipping duplicate filing: {accession_no}")
                    skipped_count += 1
                    continue # Skip to the next entry in the feed
                else:
                    # Re-raise other DynamoDB errors
                    raise

            # Calculate S3 object key only if it's a new filing
            # md5 = hashlib.md5(accession_no.encode()).hexdigest()
            # object_key = f"raw/{datetime.utcnow():%Y/%m/%d}/{md5}.json"
            # Let's use a simpler structure for now, assuming accession_no is unique enough path component
            # Consider potential S3 key partitioning limits if volume is massive
            filed_dt_utc = datetime.strptime(filed_at_str, "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone.utc)
            object_key = f"raw/{filed_dt_utc:%Y/%m/%d}/{accession_no}.json"

            # 2. Put object to S3 (only if DynamoDB put succeeded)
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

            # Log latency (only for successfully processed items)
            lag = (datetime.now(timezone.utc) - filed_dt_utc).total_seconds()
            print(f"LAG_SECS {lag:.1f} for {accession_no}")

            # 3. Prepare SQS message (only if DynamoDB put succeeded)
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
            sqs_prepared_count += 1

        except Exception as err:
            # Use accession_no if available in error message
            entry_id = accession_no if accession_no else e.get('id', 'N/A')
            print(f"ERROR processing entry {entry_id}: {err}")
            # Decide if you want to continue or raise/fail - currently continues

    # Send prepared messages to SQS in batches of 10
    sqs_sent_count = 0
    if sqs_messages:
        print(f"Attempting to send {len(sqs_messages)} messages to SQS...")
        for i in range(0, len(sqs_messages), 10):
            batch = sqs_messages[i:i + 10]
            try:
                response = SQS.send_message_batch(
                    QueueUrl=SCORE_QUEUE_URL,
                    Entries=batch
                )
                sqs_sent_count += len(batch)
                if response.get('Failed'):
                    # Log specific failed message IDs if possible
                    failed_ids = [f['Id'] for f in response['Failed']]
                    print(f"ERROR SQS SendMessageBatch failed for IDs: {', '.join(failed_ids)}")
            except Exception as err:
                print(f"ERROR sending SQS batch starting at index {i}: {err}")
                # Handle partial batch failure or retry logic if needed

    print(f"Feed Entries: {len(feed.entries)}, Processed: {processed_count}, Skipped (Duplicates): {skipped_count}, S3 Puts: {s3_put_count}, SQS Prepared: {sqs_prepared_count}, SQS Sent: {sqs_sent_count}")
    return {
        "status": "ok",
        "feed_entries": len(feed.entries),
        "processed": processed_count,
        "skipped_duplicates": skipped_count,
        "s3_puts": s3_put_count,
        "sqs_prepared": sqs_prepared_count,
        "sqs_sent": sqs_sent_count
    }
