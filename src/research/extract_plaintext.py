'''
Extracts the plain text from the raw XML files in the EDGAR dataset.
The script reads JSON files from an S3 bucket, extracts the text content 
from the XML, and writes it to a new gzipped text file in another S3 bucket.
The script uses the lxml library to parse the XML and extract text, 
and the tqdm library to show progress during the extraction process.

'''

import json, gzip
import s3fs
from lxml import etree
from tqdm import tqdm

# S3 setup
s3  = s3fs.S3FileSystem()
SRC = 'edgar-edge-raw/sample/raw/'
DST = 'edgar-edge-raw/sample/text/'

def extract_plain(xml_str: str) -> str:
    parser = etree.HTMLParser()
    tree   = etree.fromstring(xml_str.encode('utf-8'), parser)
    blocks = tree.xpath('.//text()')
    return ' '.join(b.strip() for b in blocks if b.strip())

# Get all source keys
all_keys = list(s3.find(SRC))
print(f"Found {len(all_keys)} files to process.")

# Extract and write plain text with progress
for key in tqdm(all_keys, desc="Extracting text"):
    try:
        with s3.open(key, 'r') as f:
            rec = json.load(f)
        text = extract_plain(rec['content'])
        out_key = key.replace('/raw/', '/text/').rsplit('.',1)[0] + '.txt.gz'
        with s3.open(out_key, 'wb') as f:
            with gzip.GzipFile(fileobj=f, mode='w') as gz:
                gz.write(text.encode('utf-8'))
    except Exception as e:
        print(f"[Error] Failed to process {key}: {e}")
