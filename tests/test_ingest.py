import pytest
import boto3
import os
import json
from moto import mock_aws
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

# Import the handler function to be tested
# Assuming the test runs from the root directory or PYTHONPATH is set
from EDGAR_Edge.src.ingest.handler import lambda_handler

# --- Constants for Test ---
TEST_BUCKET = "test-edgar-edge-raw"
TEST_QUEUE_NAME = "test-edgar-edge-score-queue.fifo"
TEST_TABLE_NAME = "test-edgar-edge-filing-dedupe"
TEST_REGION = "us-east-1" # Moto requires a region

# --- Mock Feed Data ---
# Simulate feedparser result with duplicate entry '000-duplicate'
MOCK_FEED_DATA = {
    'entries': [
        {
            'id': 'urn:tag:sec.gov,2008:accession-number=000-unique-1',
            'updated': '2024-05-04T10:00:00-04:00', # Example timestamp
            'link': 'http://example.com/unique-1'
        },
        {
            'id': 'urn:tag:sec.gov,2008:accession-number=000-duplicate',
            'updated': '2024-05-04T10:05:00-04:00',
            'link': 'http://example.com/duplicate-1'
        },
        {
            'id': 'urn:tag:sec.gov,2008:accession-number=000-duplicate', # Duplicate ID
            'updated': '2024-05-04T10:10:00-04:00', # Different timestamp/link
            'link': 'http://example.com/duplicate-2'
        },
         {
            'id': 'urn:tag:sec.gov,2008:accession-number=000-unique-2',
            'updated': '2024-05-04T10:15:00-04:00',
            'link': 'http://example.com/unique-2'
        },
    ]
}

# --- Test Fixture ---
@pytest.fixture(scope="function")
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = TEST_REGION

@pytest.fixture(scope="function")
def mock_env_vars(aws_credentials):
    """Set up environment variables needed by the handler."""
    os.environ["RAW_BUCKET"] = TEST_BUCKET
    # We need the queue URL, which moto provides after creation
    # We'll set a placeholder here and update it inside the test
    os.environ["SCORE_QUEUE_URL"] = f"https://sqs.{TEST_REGION}.amazonaws.com/123456789012/{TEST_QUEUE_NAME}"
    os.environ["DEDUPE_TABLE"] = TEST_TABLE_NAME
    os.environ["RSS_URL"] = "mock-rss-url" # Doesn't matter as feedparser is patched

@mock_aws
@patch('EDGAR_Edge.src.ingest.handler.feedparser.parse')
def test_ingest_handler_deduplication(mock_feedparser_parse, mock_env_vars):
    """
    Tests that the handler correctly deduplicates filings based on accession_no
    using the DynamoDB table.
    """
    # --- Arrange ---
    # 1. Mock feedparser to return our test data
    mock_feedparser_parse.return_value = MagicMock(**MOCK_FEED_DATA)

    # 2. Create Mock AWS Resources
    s3_client = boto3.client("s3", region_name=TEST_REGION)
    sqs_client = boto3.client("sqs", region_name=TEST_REGION)
    dynamodb_client = boto3.client("dynamodb", region_name=TEST_REGION)
    dynamodb_resource = boto3.resource("dynamodb", region_name=TEST_REGION)

    s3_client.create_bucket(Bucket=TEST_BUCKET)
    queue_response = sqs_client.create_queue(
        QueueName=TEST_QUEUE_NAME,
        Attributes={'FifoQueue': 'true', 'ContentBasedDeduplication': 'false'}
    )
    queue_url = queue_response['QueueUrl']
    os.environ["SCORE_QUEUE_URL"] = queue_url # Update env var with actual mock URL

    dynamodb_client.create_table(
        TableName=TEST_TABLE_NAME,
        AttributeDefinitions=[{'AttributeName': 'accession_no', 'AttributeType': 'S'}],
        KeySchema=[{'AttributeName': 'accession_no', 'KeyType': 'HASH'}],
        BillingMode='PAY_PER_REQUEST',
        # Moto doesn't fully mock TTL enabling via create_table, but we test the put logic
    )
    dedupe_table = dynamodb_resource.Table(TEST_TABLE_NAME)

    # --- Act ---
    result = lambda_handler(None, None)

    # --- Assert ---
    # 1. Check Lambda result summary
    assert result["status"] == "ok"
    assert result["feed_entries"] == 4
    assert result["processed"] == 4
    assert result["skipped_duplicates"] == 1 # One duplicate skipped
    assert result["s3_puts"] == 3 # unique-1, duplicate (first time), unique-2
    assert result["sqs_prepared"] == 3
    assert result["sqs_sent"] == 3

    # 2. Check DynamoDB for deduplication entries
    # Check unique items
    item1 = dedupe_table.get_item(Key={'accession_no': '000-unique-1'}).get('Item')
    item2 = dedupe_table.get_item(Key={'accession_no': '000-duplicate'}).get('Item')
    item3 = dedupe_table.get_item(Key={'accession_no': '000-unique-2'}).get('Item')
    assert item1 is not None
    assert item2 is not None # The duplicate key should exist once
    assert item3 is not None
    assert 'ttl' in item1 # Check TTL attribute exists
    assert 'ttl' in item2
    assert 'ttl' in item3

    # Scan to ensure only 3 items total (less reliable than get_item but good sanity check)
    scan_response = dedupe_table.scan()
    assert scan_response['Count'] == 3

    # 3. Check S3 for created objects (check count and one key example)
    list_response = s3_client.list_objects_v2(Bucket=TEST_BUCKET, Prefix="raw/")
    assert list_response.get('KeyCount') == 3 # Should only be 3 objects

    # Construct expected keys based on filing dates
    dt_unique1 = datetime.strptime(MOCK_FEED_DATA['entries'][0]['updated'], "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone.utc)
    dt_duplicate = datetime.strptime(MOCK_FEED_DATA['entries'][1]['updated'], "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone.utc)
    dt_unique2 = datetime.strptime(MOCK_FEED_DATA['entries'][3]['updated'], "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone.utc)

    expected_key1 = f"raw/{dt_unique1:%Y/%m/%d}/000-unique-1.json"
    expected_key_dup = f"raw/{dt_duplicate:%Y/%m/%d}/000-duplicate.json" # Key from the *first* occurrence
    expected_key2 = f"raw/{dt_unique2:%Y/%m/%d}/000-unique-2.json"

    object_keys = [obj['Key'] for obj in list_response.get('Contents', [])]
    assert expected_key1 in object_keys
    assert expected_key_dup in object_keys
    assert expected_key2 in object_keys

    # 4. Check SQS for sent messages
    messages_received = []
    while True: # Loop to ensure we attempt to drain the queue
        msg_response = sqs_client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10, # Max allowed
            WaitTimeSeconds=1 # Short wait
        )
        if 'Messages' in msg_response:
            messages_received.extend(msg_response['Messages'])
            # Delete messages to prevent re-receiving in loop (optional for test)
            # entries_to_delete = [{'Id': msg['MessageId'], 'ReceiptHandle': msg['ReceiptHandle']} for msg in msg_response['Messages']]
            # sqs_client.delete_message_batch(QueueUrl=queue_url, Entries=entries_to_delete)
        else:
            break # No more messages

    assert len(messages_received) == 3

    # Check content of one message (e.g., the first unique one)
    received_accession_nos = set()
    for msg in messages_received:
        body = json.loads(msg['Body'])
        assert 'accession_no' in body
        assert 's3_bucket' in body
        assert 's3_key' in body
        received_accession_nos.add(body['accession_no'])

    assert '000-unique-1' in received_accession_nos
    assert '000-duplicate' in received_accession_nos # Should be present only once
    assert '000-unique-2' in received_accession_nos

# Keep the original placeholder test or remove it
# def test_placeholder():
#     """Placeholder test to ensure pytest runs in CI."""
#     assert True
