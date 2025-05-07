'''
Generate a smaller dataset from the EDGAR dataset by sampling 5% of the files.
The original 2019-April 2025 dataset was ~1.25TB which was too large for efficient experimentation.

'''


import boto3
import random
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor

# Configuration
BUCKET = 'edgar-edge-raw'
SRC_PREFIX = 'raw/'
DST_PREFIX = 'sample/raw/'

# Initialize S3 client
s3 = boto3.client('s3')

# 1. List all object keys under the 'raw/' prefix (including year subfolders)
paginator = s3.get_paginator('list_objects_v2')
page_iterator = paginator.paginate(Bucket=BUCKET, Prefix=SRC_PREFIX)

all_keys = []
for page in tqdm(page_iterator, desc='Listing objects'):
    contents = page.get('Contents', [])
    for obj in contents:
        all_keys.append(obj['Key'])

total_keys = len(all_keys)
print(f"Total objects found: {total_keys}")

# 2. Sample 5% of the keys
sample_size = int(total_keys * 0.05)
sample_keys = random.sample(all_keys, sample_size)
print(f"Sampling {sample_size} keys ({sample_size/total_keys:.2%} of total)")

# 3. Copy sampled objects to the 'sample/raw/' prefix in parallel, with progress bar
def copy_key(key):
    copy_source = {'Bucket': BUCKET, 'Key': key}
    dest_key = key.replace(SRC_PREFIX, DST_PREFIX, 1)
    s3.copy_object(Bucket=BUCKET, CopySource=copy_source, Key=dest_key)

with ThreadPoolExecutor(max_workers=32) as executor:
    list(tqdm(executor.map(copy_key, sample_keys), total=sample_size, desc='Copying objects'))

print("Sampling and copy complete!")
