import os
import pandas as pd
import torch
from datasets import Dataset, DatasetDict, load_metric
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorWithPadding
)
from peft import get_peft_model, LoraConfig, TaskType
import wandb
import numpy as np
import boto3 # For S3 upload
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
import evaluate
# --- Configuration ---
# Model
MODEL_NAME = "distilroberta-base"
# LoRA
LORA_R = 8
LORA_ALPHA = 16
LORA_DROPOUT = 0.05
# Training
OUTPUT_DIR = "./results_finetune_roberta"
LOGGING_DIR = "./logs_finetune_roberta"
WANDB_PROJECT_NAME = "edgar-edge-sprint3-finetune"
NUM_TRAIN_EPOCHS = 3 # Adjust as needed
PER_DEVICE_TRAIN_BATCH_SIZE = 16 # Adjust based on GPU memory
PER_DEVICE_EVAL_BATCH_SIZE = 64
LEARNING_RATE = 2e-5 # Standard for fine-tuning
WEIGHT_DECAY = 0.01
LOGGING_STEPS = 50
EVAL_STEPS = 200 # Evaluate more frequently
SAVE_STEPS = 200 # Save checkpoints more frequently
FP16_TRAINING = torch.cuda.is_available() # Enable fp16 if CUDA is available

# Data
# Assume edgar_labels.parquet is in the same directory or accessible path
# This file should have 'text' and 'label' columns (0 for negative, 1 for positive)
DATA_FILE_PATH = "edgar_labels.parquet" # Or path to your labeled data
SAMPLE_FRACTION = 1.0 # Use full dataset
TEST_SIZE = 0.2 # 20% of the sample for validation/hold-out
RANDOM_SEED = 42

# S3 Model Export Configuration
S3_MODEL_BUCKET = "edgar-edge-models" # Replace with your actual model bucket if different
S3_MODEL_PREFIX = "models/baseline/v0.1" # As per sprint plan hint

# --- Helper Functions ---
def upload_directory_to_s3(local_directory, bucket_name, s3_prefix):
    """Uploads the contents of a local directory to an S3 prefix."""
    s3_client = boto3.client('s3')
    print(f"Uploading directory '{local_directory}' to 's3://{bucket_name}/{s3_prefix}'...")
    try:
        for root, dirs, files in os.walk(local_directory):
            for filename in files:
                local_path = os.path.join(root, filename)
                relative_path = os.path.relpath(local_path, local_directory)
                s3_key = os.path.join(s3_prefix, relative_path)
                
                print(f"Uploading {local_path} to s3://{bucket_name}/{s3_key}")
                s3_client.upload_file(local_path, bucket_name, s3_key)
        print("Upload complete.")
        return True
    except FileNotFoundError:
        print(f"Error: Local directory '{local_directory}' not found.")
        return False
    except NoCredentialsError:
        print("Error: AWS credentials not found. Configure AWS CLI or environment variables.")
        return False
    except PartialCredentialsError:
        print("Error: Incomplete AWS credentials.")
        return False
    except Exception as e:
        print(f"An error occurred during S3 upload: {e}")
        return False

def preprocess_data(data_path, sample_fraction=1.0, test_size=0.2, seed=42):
    """Loads data, samples it, and splits into train/test."""
    print(f"Loading data from: {data_path}")
    df = pd.read_parquet(data_path)
    print(f"Full dataset shape: {df.shape}")

    # Check for 'text' and the original sentiment label column
    if not ('text' in df.columns and 'sentiment_label_3d' in df.columns):
        raise ValueError("Dataframe must contain 'text' and 'sentiment_label_3d' columns.")

    # Rename sentiment_label_3d to 'label' for consistency downstream
    df.rename(columns={'sentiment_label_3d': 'label'}, inplace=True)

    # Ensure labels are integers and map them to 0, 1, 2
    # -1 (negative) -> 0
    #  0 (neutral)  -> 1
    #  1 (positive) -> 2
    df['label'] = df['label'].replace({-1: 0, 0: 1, 1: 2}).astype(int)
    print("Label distribution after mapping:")
    print(df['label'].value_counts())

    # Ensure labels are integers (0 for negative, 1 for neutral, 2 for positive)
    # df['label'] = df['label'].astype(int) # Already done with replace and astype

    # Sample the data if sample_fraction < 1.0
    if sample_fraction < 1.0:
        df = df.sample(frac=sample_fraction, random_state=seed)
        print(f"Sampled dataset shape ({sample_fraction*100}%): {df.shape}")

    # Split into train and test
    train_df = df.sample(frac=(1-test_size), random_state=seed)
    test_df = df.drop(train_df.index)
    
    print(f"Train set size: {len(train_df)}")
    print(f"Test set size: {len(test_df)}")
    
    # Convert pandas DataFrames to Hugging Face Datasets
    train_dataset = Dataset.from_pandas(train_df)
    test_dataset = Dataset.from_pandas(test_df)
    
    return DatasetDict({"train": train_dataset, "test": test_dataset})

def tokenize_function(examples, tokenizer):
    """Tokenizes text data."""
    return tokenizer(examples["text"], truncation=True, padding="max_length", max_length=512)

def compute_metrics(eval_pred):
    """Computes F1, precision, recall, accuracy."""
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    
    metric_f1 = evaluate.load("f1")
    metric_precision = evaluate.load("precision")
    metric_recall = evaluate.load("recall")
    metric_accuracy = evaluate.load("accuracy")
    
    # Use 'weighted' average for multiclass metrics
    return {
        "f1": metric_f1.compute(predictions=predictions, references=labels, average="weighted")["f1"],
        "precision": metric_precision.compute(predictions=predictions, references=labels, average="weighted")["precision"],
        "recall": metric_recall.compute(predictions=predictions, references=labels, average="weighted")["recall"],
        "accuracy": metric_accuracy.compute(predictions=predictions, references=labels)["accuracy"],
    }

# --- Main Fine-tuning Script ---
def main():
    # Initialize WandB
    wandb.login() # Ensure you are logged in, or set WANDB_API_KEY env var
    wandb.init(project=WANDB_PROJECT_NAME, config={
        "model_name": MODEL_NAME,
        "lora_r": LORA_R,
        "lora_alpha": LORA_ALPHA,
        "learning_rate": LEARNING_RATE,
        "epochs": NUM_TRAIN_EPOCHS,
        "train_batch_size": PER_DEVICE_TRAIN_BATCH_SIZE,
        "eval_batch_size": PER_DEVICE_EVAL_BATCH_SIZE,
        "sample_fraction": SAMPLE_FRACTION,
    })

    # 1. Load and preprocess data
    print("Step 1: Loading and preprocessing data...")
    raw_datasets = preprocess_data(DATA_FILE_PATH, SAMPLE_FRACTION, TEST_SIZE, RANDOM_SEED)

    # 2. Initialize tokenizer and model
    print(f"Step 2: Initializing tokenizer and model ({MODEL_NAME})...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=3) # 3 classes: Negative, Neutral, Positive

    # 3. Tokenize datasets
    print("Step 3: Tokenizing datasets...")
    tokenized_datasets = raw_datasets.map(lambda x: tokenize_function(x, tokenizer), batched=True)
    
    # Remove original text column to avoid issues with data collator
    tokenized_datasets = tokenized_datasets.remove_columns(["text"])
    if '__index_level_0__' in tokenized_datasets['train'].column_names: # handle pandas index
        tokenized_datasets = tokenized_datasets.remove_columns(['__index_level_0__'])


    # Data collator
    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    # 4. Configure LoRA (PEFT)
    print("Step 4: Configuring LoRA (PEFT)...")
    peft_config = LoraConfig(
        task_type=TaskType.SEQ_CLS, # Sequence Classification
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=["query", "value"] # Common target modules for RoBERTa-like models, may need adjustment
    )
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    # 5. Define Training Arguments
    print("Step 5: Defining training arguments...")
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        logging_dir=LOGGING_DIR,
        num_train_epochs=NUM_TRAIN_EPOCHS,
        per_device_train_batch_size=PER_DEVICE_TRAIN_BATCH_SIZE,
        per_device_eval_batch_size=PER_DEVICE_EVAL_BATCH_SIZE,
        learning_rate=LEARNING_RATE,
        weight_decay=WEIGHT_DECAY,
        eval_strategy="steps", # Evaluate at each `eval_steps`
        eval_steps=EVAL_STEPS,
        save_strategy="steps",       # Save at each `save_steps`
        save_steps=SAVE_STEPS,
        logging_steps=LOGGING_STEPS,
        load_best_model_at_end=True, # Load the best model found during training
        metric_for_best_model="f1",  # Use F1 score to determine the best model
        greater_is_better=True,
        fp16=FP16_TRAINING,
        report_to="wandb",           # Report metrics to WandB
        seed=RANDOM_SEED,
        push_to_hub=False,           # Not pushing to HF Hub for now
    )

    # 6. Initialize Trainer
    print("Step 6: Initializing Trainer...")
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_datasets["train"],
        eval_dataset=tokenized_datasets["test"],
        tokenizer=tokenizer,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
    )

    # 7. Start Training
    print("Step 7: Starting training...")
    train_result = trainer.train()
    print("Training complete.")

    # 8. Evaluate the best model
    print("Step 8: Evaluating the best model on the test set...")
    eval_results = trainer.evaluate(eval_dataset=tokenized_datasets["test"])
    print(f"Evaluation results: {eval_results}")
    wandb.log({"final_evaluation_metrics": eval_results}) # Log final eval to WandB

    # 9. Save the best model and tokenizer
    # The trainer already saves checkpoints, but we can save the best one explicitly
    best_model_path = os.path.join(OUTPUT_DIR, "best_model_checkpoint")
    print(f"Saving the best model to {best_model_path}...")
    trainer.save_model(best_model_path) # Saves LoRA adapters and config
    tokenizer.save_pretrained(best_model_path)
    print(f"Best model and tokenizer saved to {best_model_path}")
    
    # Log F1 score for KPI check (ML-3.1: F1 >= 0.55)
    final_f1 = eval_results.get("eval_f1", 0)
    print(f"Final F1 score on hold-out: {final_f1:.4f}")
    if final_f1 >= 0.55:
        print(f"SUCCESS: Fine-tune F1 KPI met (F1={final_f1:.4f} >= 0.55)")
    else:
        print(f"NOTE: Fine-tune F1 KPI NOT met (F1={final_f1:.4f} < 0.55). Consider adjustments.")

    # 10. Upload the best model to S3 (ML-3.2)
    print(f"Step 10: Uploading best model from {best_model_path} to S3...")
    if os.path.exists(best_model_path):
        upload_success = upload_directory_to_s3(best_model_path, S3_MODEL_BUCKET, S3_MODEL_PREFIX)
        if upload_success:
            print(f"Model successfully uploaded to s3://{S3_MODEL_BUCKET}/{S3_MODEL_PREFIX}")
        else:
            print(f"Failed to upload model to S3.")
    else:
        print(f"Error: Best model path {best_model_path} does not exist. Cannot upload to S3.")

    wandb.finish()
    print("Script finished.")

if __name__ == "__main__":
    # This script assumes that 'edgar_labels.parquet' is available
    # and that you have CUDA-enabled GPU if FP16_TRAINING is True.
    # You might need to run `wandb login` in your terminal first.
    
    # Create dummy data for testing if DATA_FILE_PATH doesn't exist
    if not os.path.exists(DATA_FILE_PATH):
        print(f"Warning: {DATA_FILE_PATH} not found. Creating dummy data for script execution.")
        num_samples = 201 # Ensure we get all three classes -1, 0, 1
        print(f"Warning: {DATA_FILE_PATH} not found. Creating dummy data for script execution.")
        num_samples = 201 # Ensure we get all three classes -1, 0, 1
        dummy_texts = [f"This is sample text number {i}. This is some sample text content for testing purposes." for i in range(num_samples)] # Added sample text content
        # Generate labels -1, 0, 1 cyclically
        dummy_labels = [(i % 3) - 1 for i in range(num_samples)] # Generate labels -1, 0, 1
        dummy_df = pd.DataFrame({'text': dummy_texts, 'sentiment_label_3d': dummy_labels}) # Use 'sentiment_label_3d' column name
        dummy_df.to_parquet(DATA_FILE_PATH, index=False)
        print(f"Dummy data created at {DATA_FILE_PATH}")

    main()
