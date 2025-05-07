
# Dataset processing pipeline (preparing for training run)
1. Download the data from EDGAR to s3 (~1.25TB for 2019-April 2025) 
(EDGAR-Edge/src/ingest/async_backfill.py)
2. Generate a smaller dataset by taking a random sample (5%) (~60GB)(generate_smaller_dataset.py)
3. Remove the 100 largest outlier objects (~3x size reduction -> 21GB)
(delete_whales.py)
4. Extract plaintext from xml 
(extract_plaintext.py)
5. Label the data and output as parquet (experiment with different approaches to labeling)
(generate_labels.py)

