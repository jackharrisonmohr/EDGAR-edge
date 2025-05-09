import json
import gzip
import s3fs
from lxml import etree
from tqdm import tqdm

# S3 setup
s3  = s3fs.S3FileSystem()
SRC = 'edgar-edge-raw/raw/'
DST = 'edgar-edge-raw/text/'

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
    # determine the output key
    out_key = key.replace('/raw/', '/text/').rsplit('.', 1)[0] + '.txt.gz'

    # skip if already exists
    if s3.exists(out_key):
        tqdm.write(f"Skipping (already done): {out_key}")
        continue

    try:
        # read the raw JSON
        with s3.open(key, 'r') as f:
            rec = json.load(f)

        # extract plain text
        text = extract_plain(rec['content'])

        # write to gzipped text file
        with s3.open(out_key, 'wb') as f:
            with gzip.GzipFile(fileobj=f, mode='w') as gz:
                gz.write(text.encode('utf-8'))

    except Exception as e:
        tqdm.write(f"[Error] Failed to process {key}: {e}")
