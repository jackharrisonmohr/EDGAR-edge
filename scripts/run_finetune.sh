#!/bin/bash
set -e

# Activate virtual environment
echo ">>> Activating virtual environment..."
source ~/edgarenv/bin/activate

# Navigate to project root
cd ~/EDGAR-Edge

# Check that the labels file exists
if [ ! -f "edgar_labels.parquet" ]; then
  echo "❌ ERROR: 'edgar_labels.parquet' not found in current directory."
  echo "💡 Make sure you've uploaded the labeled dataset via S3 or SCP."
  exit 1
fi

# Log start time
echo ">>> Starting fine-tuning at $(date)"
echo ">>> Output will be saved to ./results_finetune_roberta/ and uploaded to S3"

# Run the training script using Poetry
poetry run python src/research/finetune_roberta_script.py

# Log end time
echo "✅ Fine-tuning completed at $(date)"
