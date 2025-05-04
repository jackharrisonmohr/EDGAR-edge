import argparse
import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path
import time
from datetime import datetime, timedelta
import logging
import pyarrow as pa
import pyarrow.parquet as pq
from concurrent.futures import ThreadPoolExecutor, as_completed
import boto3
import json
from io import BytesIO
# Optional: from scipy import stats # If doing regression for abnormal returns

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
CIK_TICKER_MAP_PATH = Path(__file__).parent.parent.parent / "ticker.txt" # Assumes script is in src/research/
OUTPUT_DIR = Path(__file__).parent.parent.parent / "labels"
OUTPUT_FILE = OUTPUT_DIR / "edgar_labels.parquet"
RAW_FILINGS_BUCKET = "edgar-edge-raw" # TODO: Get from config/env var
SPX_TICKER = "^GSPC" # Ticker for S&P 500 index
ABNORMAL_RETURN_DAYS = 3 # Number of days forward to calculate return
LABEL_THRESHOLD = 0.008 # +/- 0.8% for positive/negative label

# --- Helper Functions ---

def load_cik_ticker_map(file_path: Path) -> dict:
    """Loads the CIK to Ticker mapping from the SEC file."""
    logger.info(f"Loading CIK-Ticker map from: {file_path}")
    if not file_path.exists():
        logger.error(f"CIK-Ticker map file not found at {file_path}")
        return {}

    cik_to_ticker = {}
    try:
        with open(file_path, 'r') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) == 2:
                    ticker, cik = parts
                    # SEC file has ticker first, then CIK. We want CIK as key.
                    # Ensure CIK is integer for consistent lookup if needed elsewhere
                    try:
                        cik_int = int(cik)
                        # Store ticker in uppercase for consistency with yfinance
                        cik_to_ticker[str(cik_int)] = ticker.upper()
                    except ValueError:
                        logger.warning(f"Could not parse CIK '{cik}' as integer for ticker '{ticker}'. Skipping.")
                else:
                     logger.warning(f"Skipping malformed line in ticker file: {line.strip()}")

    except Exception as e:
        logger.error(f"Error reading CIK-Ticker map file: {e}")
        return {}

    logger.info(f"Loaded {len(cik_to_ticker)} CIK-Ticker mappings.")
    return cik_to_ticker


def list_s3_filing_metadata(bucket: str, start_date: datetime, end_date: datetime):
    """
    Lists filing metadata (assuming JSON objects with cik, filed_at)
    from S3 within a date range.
    NOTE: This could be slow for large date ranges. Consider alternative metadata source.
    """
    logger.info(f"Listing S3 metadata from {start_date.date()} to {end_date.date()} in bucket {bucket}")
    s3 = boto3.client('s3')
    metadata_list = []
    current_date = start_date
    while current_date <= end_date:
        prefix = f"raw/{current_date.strftime('%Y/%m/%d')}/"
        logger.debug(f"Checking prefix: {prefix}")
        paginator = s3.get_paginator('list_objects_v2')
        try:
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        # Basic check, assumes JSON files contain needed keys
                        if obj['Key'].endswith('.json'):
                             metadata_list.append({'s3_key': obj['Key']})
                             # TODO: Optionally read CIK/filed_at here to avoid later reads? Tradeoff: slower listing.
        except ClientError as e:
            logger.error(f"Error listing S3 objects for prefix {prefix}: {e}")
        current_date += timedelta(days=1)
        # time.sleep(0.01) # Avoid aggressive listing?

    logger.info(f"Found {len(metadata_list)} potential filing objects in S3.")
    return metadata_list


def fetch_metadata_from_s3(bucket: str, s3_key: str) -> dict | None:
    """Fetches and parses the JSON metadata from a single S3 object."""
    s3 = boto3.client('s3')
    try:
        response = s3.get_object(Bucket=bucket, Key=s3_key)
        content = response['Body'].read()
        data = json.loads(content.decode('utf-8'))
        # Ensure required keys are present
        if 'accession_no' in data and 'cik' in data and 'filed_at' in data:
             # Convert filed_at to datetime object
             data['filed_at_dt'] = pd.to_datetime(data['filed_at']).tz_convert(None) # Store as naive UTC
             data['s3_key'] = s3_key # Add key for reference
             return data
        else:
             logger.warning(f"Missing required keys in {s3_key}. Skipping.")
             return None
    except Exception as e:
        logger.error(f"Error fetching/parsing {s3_key}: {e}")
        return None


def fetch_all_metadata(bucket: str, s3_keys: list, max_workers: int) -> pd.DataFrame:
    """Fetches metadata for multiple S3 keys concurrently."""
    logger.info(f"Fetching metadata for {len(s3_keys)} S3 keys using {max_workers} workers...")
    all_metadata = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_key = {executor.submit(fetch_metadata_from_s3, bucket, key_info['s3_key']): key_info['s3_key'] for key_info in s3_keys}
        for i, future in enumerate(as_completed(future_to_key)):
            key = future_to_key[future]
            try:
                result = future.result()
                if result:
                    all_metadata.append(result)
            except Exception as exc:
                logger.error(f"Metadata fetch for {key} generated an exception: {exc}")
            if (i + 1) % 1000 == 0:
                 logger.info(f"Fetched metadata for {i+1}/{len(s3_keys)} keys...")

    logger.info(f"Successfully fetched metadata for {len(all_metadata)} filings.")
    if not all_metadata:
        return pd.DataFrame()
    return pd.DataFrame(all_metadata)


def fetch_price_data(tickers: list, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetches adjusted closing prices using yfinance."""
    logger.info(f"Fetching price data for {len(tickers)} tickers from {start_date} to {end_date}...")
    # Add buffer for calculating forward returns
    start_dt_buffered = pd.to_datetime(start_date) - timedelta(days=10) # Buffer for lookback if needed
    end_dt_buffered = pd.to_datetime(end_date) + timedelta(days=10) # Buffer for forward returns

    try:
        prices = yf.download(tickers, start=start_dt_buffered, end=end_dt_buffered, progress=False)['Adj Close']
        if prices.empty:
             logger.warning("yfinance returned empty DataFrame for prices.")
             return pd.DataFrame()
        # Handle cases where only one ticker is downloaded (returns Series)
        if isinstance(prices, pd.Series):
            prices = prices.to_frame(name=tickers[0])
        logger.info(f"Price data shape: {prices.shape}")
        prices.index = pd.to_datetime(prices.index).tz_localize(None) # Ensure naive datetime index
        return prices.dropna(axis=1, how='all') # Drop tickers with no data
    except Exception as e:
        logger.error(f"Error fetching price data: {e}")
        return pd.DataFrame()


def calculate_abnormal_returns(prices: pd.DataFrame, spx_ticker: str, days: int) -> pd.DataFrame:
    """
    Calculates N-day forward abnormal returns.
    Simplistic version: Ticker Return - SPX Return.
    TODO: Implement regression-based alpha if needed.
    """
    logger.info(f"Calculating {days}-day forward abnormal returns...")
    if spx_ticker not in prices.columns:
        logger.error(f"SPX ticker '{spx_ticker}' not found in price data.")
        return pd.DataFrame()

    # Calculate daily percentage returns
    returns = prices.pct_change().dropna(how='all')

    # Calculate N-day forward cumulative returns
    # Shift(-days) brings future returns to the current row
    forward_returns = (1 + returns).rolling(window=days).apply(np.prod, raw=True) - 1
    forward_returns = forward_returns.shift(-days)

    # Calculate abnormal returns (Ticker Forward Return - SPX Forward Return)
    spx_forward_returns = forward_returns[spx_ticker]
    abnormal_returns = forward_returns.subtract(spx_forward_returns, axis=0)
    abnormal_returns = abnormal_returns.drop(columns=[spx_ticker]) # Drop SPX column itself

    logger.info(f"Calculated abnormal returns shape: {abnormal_returns.shape}")
    return abnormal_returns


def assign_labels(abnormal_return: float, threshold: float) -> int:
    """Assigns labels based on abnormal return and threshold."""
    if pd.isna(abnormal_return):
        return 0 # Or handle NaN differently? Maybe drop these filings later.
    elif abnormal_return > threshold:
        return 1
    elif abnormal_return < -threshold:
        return -1
    else:
        # According to plan, drop near-zero moves. We'll assign 0 for now
        # and potentially filter later, or return None/NaN.
        return 0


# --- Main Execution ---

def main(start_date_str, end_date_str, max_workers):
    """Main function to generate labels."""

    # 1. Load CIK-Ticker Map
    cik_ticker_map = load_cik_ticker_map(CIK_TICKER_MAP_PATH)
    if not cik_ticker_map:
        return

    # 2. Find and Fetch Filing Metadata from S3
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    s3_keys_info = list_s3_filing_metadata(RAW_FILINGS_BUCKET, start_date, end_date)
    if not s3_keys_info:
        logger.warning("No filing metadata found in S3 for the specified date range.")
        return

    filings_df = fetch_all_metadata(RAW_FILINGS_BUCKET, s3_keys_info, max_workers)
    if filings_df.empty:
        logger.warning("Could not fetch any valid metadata from S3 objects.")
        return

    # Add ticker using the map (handle missing CIKs)
    filings_df['ticker'] = filings_df['cik'].astype(str).map(cik_ticker_map)
    original_count = len(filings_df)
    filings_df.dropna(subset=['ticker'], inplace=True)
    logger.info(f"Mapped tickers for {len(filings_df)}/{original_count} filings.")
    if filings_df.empty:
        return

    # Ensure filed_at_dt is datetime
    filings_df['filed_at_dt'] = pd.to_datetime(filings_df['filed_at_dt'])

    # 3. Fetch Price Data
    unique_tickers = filings_df['ticker'].unique().tolist()
    all_tickers_to_fetch = unique_tickers + [SPX_TICKER]
    min_filing_date = filings_df['filed_at_dt'].min().strftime('%Y-%m-%d')
    max_filing_date = filings_df['filed_at_dt'].max().strftime('%Y-%m-%d')

    price_data = fetch_price_data(all_tickers_to_fetch, min_filing_date, max_filing_date)
    if price_data.empty:
        logger.error("Failed to fetch price data. Cannot proceed.")
        return

    # Filter filings_df to only include tickers we got price data for
    available_tickers = price_data.columns.tolist()
    filings_df = filings_df[filings_df['ticker'].isin(available_tickers)]
    logger.info(f"Proceeding with {len(filings_df)} filings that have available price data.")
    if filings_df.empty:
        return

    # 4. Calculate Abnormal Returns
    abnormal_returns_df = calculate_abnormal_returns(price_data, SPX_TICKER, ABNORMAL_RETURN_DAYS)
    if abnormal_returns_df.empty:
        logger.error("Failed to calculate abnormal returns.")
        return

    # 5. Merge Abnormal Returns with Filings
    # We need to align the filing date with the *start* date of the forward abnormal return period.
    # The abnormal_returns_df index represents the date *before* the N-day period starts.
    filings_df['join_date'] = filings_df['filed_at_dt'].dt.normalize() # Use date part for joining

    # Reshape abnormal returns for merging: date, ticker, abn_return
    abnormal_returns_long = abnormal_returns_df.stack().reset_index()
    abnormal_returns_long.columns = ['join_date', 'ticker', f'abn_ret_{ABNORMAL_RETURN_DAYS}d']
    abnormal_returns_long['join_date'] = pd.to_datetime(abnormal_returns_long['join_date'])

    # Merge based on ticker and the filing date
    labeled_filings = pd.merge(
        filings_df,
        abnormal_returns_long,
        on=['join_date', 'ticker'],
        how='left'
    )

    # 6. Assign Labels
    label_col = f'sentiment_label_{ABNORMAL_RETURN_DAYS}d'
    abn_ret_col = f'abn_ret_{ABNORMAL_RETURN_DAYS}d'
    labeled_filings[label_col] = labeled_filings[abn_ret_col].apply(
        assign_labels, threshold=LABEL_THRESHOLD
    )

    # 7. Final Selection and Save
    output_columns = [
        'accession_no',
        'cik',
        'ticker',
        'filed_at_dt', # Keep datetime object
        abn_ret_col,
        label_col
    ]
    final_df = labeled_filings[output_columns].copy()
    final_df.rename(columns={'filed_at_dt': 'filed_at'}, inplace=True) # Rename for clarity

    # Drop rows where label could not be calculated (e.g., NaN abnormal return)
    final_df.dropna(subset=[label_col, abn_ret_col], inplace=True)
    # Optional: Drop rows with label 0 if required by plan
    # final_df = final_df[final_df[label_col] != 0]

    logger.info(f"Generated labels for {len(final_df)} filings.")
    logger.info(f"Label distribution:\n{final_df[label_col].value_counts(normalize=True)}")

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save to Parquet
    try:
        logger.info(f"Saving final labels to: {OUTPUT_FILE}")
        table = pa.Table.from_pandas(final_df, preserve_index=False)
        pq.write_table(table, OUTPUT_FILE, compression='snappy')
        logger.info("Successfully saved labels to Parquet.")
    except Exception as e:
        logger.error(f"Failed to save labels to Parquet: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate sentiment labels for SEC filings based on forward abnormal returns.")
    parser.add_argument("--start-date", required=True, help="Start date for filings processing (YYYY-MM-DD).")
    parser.add_argument("--end-date", required=True, help="End date for filings processing (YYYY-MM-DD).")
    parser.add_argument("--workers", type=int, default=8, help="Number of concurrent workers for fetching metadata.")
    # TODO: Add args for bucket, output file, threshold etc. if needed

    args = parser.parse_args()

    logger.info(f"Starting label generation from {args.start_date} to {args.end_date}...")
    main(args.start_date, args.end_date, args.workers)
    logger.info("Label generation script finished.")
