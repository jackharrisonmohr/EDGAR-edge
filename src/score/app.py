from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .dummy_model import DummySentimentModel # Import the new model class
import boto3
import os
import functools # For LRU cache
import json # For parsing S3 JSON content if needed
from prometheus_fastapi_instrumentator import Instrumentator # For Prometheus metrics
from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
from peft import PeftModel, PeftConfig
import torch

# --- Configuration & Globals ---
# S3 Client and Bucket Name
# This assumes the Lambda and Fargate task have permissions to this bucket.
S3_CLIENT = boto3.client("s3")
RAW_FILINGS_BUCKET = os.environ.get("RAW_BUCKET", "edgar-edge-raw") # Default, can be overridden
MAX_FILE_SIZE_BYTES = 100 * 1024  # 100 KB as per APP-3.4

# LRU Cache for S3 content (maxsize can be tuned)
@functools.lru_cache(maxsize=128)
def get_s3_content(s3_key: str) -> str | None:
    """
    Fetches content from S3, caches it, and limits file size.
    Returns plaintext content or None if an error occurs or file is too large.
    """
    if not RAW_FILINGS_BUCKET:
        print("Error: RAW_BUCKET environment variable not set.")
        return None
    try:
        print(f"Fetching from S3: s3://{RAW_FILINGS_BUCKET}/{s3_key}")
        response = S3_CLIENT.get_object(Bucket=RAW_FILINGS_BUCKET, Key=s3_key)
        
        content_length = response.get('ContentLength', 0)
        if content_length > MAX_FILE_SIZE_BYTES:
            print(f"File s3://{RAW_FILINGS_BUCKET}/{s3_key} is too large ({content_length} bytes), skipping.")
            return None # Or raise HTTPException(status_code=413, detail="File too large")

        file_content_bytes = response['Body'].read()
        
        # Assuming the raw files are JSON with a 'text' field for plaintext
        # If they are already plaintext, this json.loads part can be removed/adjusted.
        try:
            # Attempt to parse as JSON and extract 'text' field
            # This matches the structure from the ingest lambda's s3_body
            data = json.loads(file_content_bytes.decode('utf-8'))
            if 'text' in data: # If 'text' field exists (as per project overview for raw_filings)
                return data['text']
            else: # If it's just a JSON blob without 'text', or already plaintext
                 # For now, let's assume if no 'text' field, the whole content is the text.
                 # This part needs to align with actual S3 object content.
                 # If files are stored as pure plaintext, then just:
                 # return file_content_bytes.decode('utf-8')
                 print(f"Warning: 'text' field not found in JSON for {s3_key}. Returning full decoded content.")
                 return file_content_bytes.decode('utf-8')
        except json.JSONDecodeError:
            # If it's not JSON, assume it's already plaintext
            print(f"Content for {s3_key} is not JSON, assuming plaintext.")
            return file_content_bytes.decode('utf-8')
        except UnicodeDecodeError:
            print(f"Error decoding content for {s3_key} as UTF-8.")
            return None

    except Exception as e:
        print(f"Error fetching S3 object s3://{RAW_FILINGS_BUCKET}/{s3_key}: {e}")
        return None


# Define the request body for the scoring endpoint
class ScoreRequest(BaseModel):
    s3_key: str

# Define the response body for the scoring endpoint
class ScoreResponse(BaseModel):
    s3_key: str
    sentiment_score: float
    model_version: str

app = FastAPI(
    title="EDGAR-Edge Scoring Service",
    description="Provides sentiment scores for SEC filings.",
    version="0.1.0"
)

# Instrument the app with Prometheus metrics
# This should be done before defining routes that you want to instrument
Instrumentator().instrument(app).expose(app, include_in_schema=True, should_gzip=True)

# Instantiate the dummy model
# This could be loaded at startup, e.g. using FastAPI's lifespan events for a real model
# sentiment_model = DummySentimentModel() # Will be replaced by dynamic loading
# MODEL_VERSION = sentiment_model.get_model_version() # Will be replaced

# --- Model Loading ---
# Environment variables
USE_REAL_MODEL_ENV = os.environ.get("USE_REAL_MODEL", "false").lower() == "true"
# MODEL_S3_URI_ENV = os.environ.get("MODEL_S3_URI") # Already in ecs.tf, points to model dir in S3
# For now, let's assume the model is at a fixed local path in the container
# This path should correspond to where the model is downloaded/placed in the Docker image or a volume.
LOCAL_MODEL_PATH = os.environ.get("LOCAL_MODEL_PATH", "/app/model_checkpoint") # Default local path

active_model = None
active_model_version = None
active_tokenizer = None
sentiment_pipeline = None

def load_fine_tuned_model(model_path: str):
    global active_tokenizer, sentiment_pipeline, active_model_version
    try:
        print(f"Loading fine-tuned model from: {model_path}")
        # Load the PEFT config first to get the base model name
        # config = PeftConfig.from_pretrained(model_path) # This might be needed if base_model_name_or_path is not in adapter_config.json
        
        # Load the base model
        # Assuming the base model name is known or can be inferred.
        # For DistilRoBERTa, it's "distilroberta-base".
        # This should ideally come from the PEFT config if not hardcoded.
        # For simplicity, let's assume adapter_config.json contains base_model_name_or_path
        base_model_name = "distilroberta-base" # Fallback, try to get from config
        try:
            with open(os.path.join(model_path, "adapter_config.json"), "r") as f:
                adapter_config = json.load(f)
                base_model_name = adapter_config.get("base_model_name_or_path", base_model_name)
        except Exception as e:
            print(f"Could not read base_model_name_or_path from adapter_config.json: {e}. Using default '{base_model_name}'.")

        base_model = AutoModelForSequenceClassification.from_pretrained(base_model_name, num_labels=2)
        
        # Load the PEFT model (LoRA adapters)
        peft_model = PeftModel.from_pretrained(base_model, model_path)
        active_tokenizer = AutoTokenizer.from_pretrained(model_path) # Tokenizer should be saved with adapter

        # Create a pipeline for easier inference
        # Ensure the device is correctly set (cpu or cuda if available)
        device = 0 if torch.cuda.is_available() else -1 
        sentiment_pipeline = pipeline(
            "text-classification", 
            model=peft_model, 
            tokenizer=active_tokenizer,
            device=device,
            return_all_scores=True # Returns scores for all labels
        )
        active_model_version = f"fine_tuned_peft_{model_path.split('/')[-1]}" # e.g., fine_tuned_peft_v0.1
        print(f"Successfully loaded fine-tuned model: {active_model_version}")
        return True
    except Exception as e:
        print(f"Error loading fine-tuned model from {model_path}: {e}")
        sentiment_pipeline = None # Ensure pipeline is None if loading fails
        active_model_version = "error_loading_fine_tuned"
        return False

def initialize_model():
    global active_model, active_model_version, sentiment_model # Use the global dummy model instance
    
    if USE_REAL_MODEL_ENV:
        print(f"USE_REAL_MODEL is true. Attempting to load fine-tuned model from {LOCAL_MODEL_PATH}.")
        if os.path.exists(LOCAL_MODEL_PATH):
            if load_fine_tuned_model(LOCAL_MODEL_PATH):
                return # Successfully loaded fine-tuned model
            else:
                print(f"Failed to load fine-tuned model. Falling back to dummy model.")
        else:
            print(f"Fine-tuned model path {LOCAL_MODEL_PATH} not found. Falling back to dummy model.")
    else:
        print("USE_REAL_MODEL is false. Using dummy model.")

    # Fallback to dummy model
    sentiment_model = DummySentimentModel() # This is the class instance
    active_model = sentiment_model # Keep a reference for consistency if needed elsewhere
    active_model_version = sentiment_model.get_model_version()
    print(f"Initialized with dummy model: {active_model_version}")

# Initialize model on startup
# FastAPI lifespan events could be used for more robust startup/shutdown logic
initialize_model()


@app.get("/health", summary="Health Check", description="Returns a 200 OK if the service is healthy.")
async def health_check():
    """
    Health check endpoint.
    """
    return {"status": "healthy", "model_version": active_model_version}

@app.post("/v1/score", response_model=ScoreResponse, summary="Score Filing Sentiment")
async def score_filing(request: ScoreRequest):
    """
    Scores the sentiment of a filing based on its S3 key.

    - **s3_key**: The S3 key of the filing to score (e.g., "raw/2023/05/08/some-accession-no.json").
                  The service will fetch this file from S3.
    """
    print(f"Received scoring request for S3 key: {request.s3_key}")

    # In a real application, you would:
    # 1. Fetch the content from S3 using request.s3_key
    #    - This will be implemented in APP-3.4 (S3 fetch & cache layer)
    #    - For now, we'll use a placeholder text.
    # 2. Preprocess the text.
    # 3. Run the sentiment model.

    if not request.s3_key:
        raise HTTPException(status_code=400, detail="s3_key must be provided.")

    # Fetch content from S3 using the cached function
    text_content = get_s3_content(request.s3_key)

    if text_content is None:
        # get_s3_content would have logged the error or size issue
        # Or if file was too large and returned None
        # Check if it was due to size specifically if get_s3_content is modified to indicate that
        # For now, assume any None is a fetch failure or unprocessable content
        raise HTTPException(status_code=404, detail=f"Could not retrieve or process content for S3 key: {request.s3_key}. It might be too large, not found, or in an unexpected format.")

    print(f"Processing content for S3 key: {request.s3_key} (length: {len(text_content)})")
    
    # Perform sentiment analysis
    try:
        if sentiment_pipeline: # Use fine-tuned model if pipeline is available
            # The pipeline returns a list of dicts, e.g., [{'label': 'LABEL_0', 'score': 0.00...}, {'label': 'LABEL_1', 'score': 0.99...}]
            # We need to map LABEL_0 (negative) and LABEL_1 (positive) to a single score from -1 to 1.
            # Assuming LABEL_1 is positive and LABEL_0 is negative.
            results = sentiment_pipeline(text_content, truncation=True, max_length=512) # Ensure truncation
            score_label_1 = 0.0
            score_label_0 = 0.0
            for item in results[0]: # Results is a list containing a list of dicts
                if item['label'] == 'LABEL_1': # Positive
                    score_label_1 = item['score']
                elif item['label'] == 'LABEL_0': # Negative
                    score_label_0 = item['score']
            
            # Convert to a single score: positive_score - negative_score
            # This ranges from -1 (if LABEL_0 is 1.0) to +1 (if LABEL_1 is 1.0)
            sentiment_score = score_label_1 - score_label_0
            
        elif active_model: # Fallback to dummy model's predict method
            sentiment_score = active_model.predict(text_content)
        else: # Should not happen if initialize_model worked
            raise HTTPException(status_code=500, detail="Scoring model not available.")
            
    except Exception as e:
        print(f"Error during sentiment scoring for {request.s3_key}: {e}")
        raise HTTPException(status_code=500, detail=f"Error scoring sentiment: {str(e)}")

    print(f"Sentiment score for {request.s3_key}: {sentiment_score:.4f}")

    return ScoreResponse(
        s3_key=request.s3_key,
        sentiment_score=sentiment_score,
        model_version=active_model_version
    )

if __name__ == "__main__":
    import uvicorn
    # This is for local development/testing directly with uvicorn
    # For production, Gunicorn + Uvicorn workers will be used (APP-3.3)
    uvicorn.run(app, host="0.0.0.0", port=8000)
