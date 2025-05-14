
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

# Training
1. Rent an instance and ssh in. I used one on VastAI with an RTX4090 GPU. 
2. Run setup-gpu-instance.sh on the instance. Assumes your instance comes pre-installed with ubuntu and pytorch. 
`git clone http://github.com/jackharrisonmohr/EDGAR-Edge && cd EDGAR-Edge && scripts/setup-gpu-instance.sh`
3. Download the training data from s3 (you can use curl) 
`curl -O https://edgar-edge-labelled-parquets.s3.us-east-1.amazonaws.com/edgar_labels_sample_dataset.parquet`
