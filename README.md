# EDGAR‑Edge

**Streaming NLP Factor Engine for 8‑K / 10‑K Filings**

> A production‑grade pipeline that ingests SEC filings in near‑real‑time, runs fast sentiment inference with a fine‑tuned DistilRoBERTa model, constructs a z‑scored daily sentiment factor, and backs it against SPX sectors—all hosted with Terraform, Docker, and AWS serverless infrastructure.

---

## ✅ Key Highlights

- **Latency & Throughput**: < 60 s ingest from SEC → S3, p95 inference < 200 ms on t4g.small, sustain 300 filings/hr
- **Signal Quality**: 6‑mo IC ≥ 0.05 (t‑stat ≥ 3), transaction‑cost‑adjusted Sharpe > 1
- **Engineering Depth**: AWS Lambda + SQS + Fargate + Terraform + GitHub Actions CI/CD
- **Research Rigor**: walk‑forward validation, sector/beta neutralisation, bootstrap CIs, regime stress tests
- **Presentation**: public Streamlit dashboard, PDF white‑paper, 2‑min demo video

---

## 📦 Architecture Overview

```text
    RSS / API Feed
          │
          ▼
    Ingest Lambda ──► S3 `raw/`
          │            │
          ▼            ▼
       SQS FIFO   CloudWatch Metrics
          │
          ▼
    Fargate Scoring ──► S3 `scored/`
          │
          ▼
  Athena / Glue Catalog
          │
          ▼
Airflow Factor Builder ──► S3 `factors/` + PDF reports
          │
          ▼
Streamlit Dashboard
          │
          ▼
Grafana / Prometheus Monitoring
```

For a detailed diagram, see [`docs/architecture.md`](docs/architecture.md).

---

## 🏁 Quickstart
> (live demo to come. So far this quickstart just allows you to deploy the infrastructure on AWS and pull the SEC filings from the EDGAR RSS feed into an s3 bucket in real-time. - JHM, 2025-04-27)
### Accessing EDGAR Data

For more information on accessing the EDGAR database, refer to the official SEC documentation: [Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).

### Prerequisites

- **AWS Account** with permissions to create: S3, Lambda, SQS, Fargate, IAM, CloudWatch
- **Terraform v1.4+**
- **Docker**
- **Poetry** or **pipenv** for Python dependencies

### 1. Clone the repo

```bash
git clone https://github.com/jackharrisonmohr/EDGAR-edge
cd EDGAR-edge
```

### 2. Configure AWS credentials

```bash
aws-vault exec myprofile -- terraform init infra/
```

Or export via environment:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-east-1
```

### 3. Provision infrastructure

```bash
cd infra
terraform apply -auto-approve
```

### 4. Package & deploy the ingest Lambda

```bash
make lambda-package            # builds ingest zip
terraform apply -auto-approve # picks up new lambda code
```

### 5. Run the demo

```bash
# Ingest PoC: monitor S3 bucket for new `raw/` objects
aws s3 ls s3://edgar-edge-raw/ --recursive | tail -n 10

# View latency metrics in CloudWatch Logs Insights
```

---

---

## 🎉 Milestone 1: Real-time Ingest Pipeline (Completed Week 1)

Successfully established the foundational real-time data ingestion pipeline, achieving the goal of landing raw SEC filings in an S3 bucket within 60 seconds of their publication on the EDGAR RSS feed.

**Key Achievements:**

- **Infrastructure Setup:** Provisioned core AWS resources (S3 buckets for raw data and logs, IAM execution role, CloudWatch log group) using Terraform (`infra/`).
- **SEC Feed Integration:** Developed and tested a Python script (`src/ingest/rss_poc.py`) to parse the EDGAR 8-K RSS feed.
- **Lambda Puller:** Deployed an AWS Lambda function (`src/ingest/handler.py`) triggered every minute by EventBridge to poll the RSS feed and write new filing metadata to the `edgar-edge-raw` S3 bucket.
- **Latency Measurement:** Instrumented the Lambda function to calculate and log the ingest latency (`LAG_SECS`) from SEC publication time to S3 write time.
- **Verification:** Confirmed end-to-end functionality through smoke tests, verifying timely object creation in S3 and monitoring latency via CloudWatch Logs Insights, achieving `p50 lag < 60s`.
- **CI/CD Foundation:** Implemented a basic GitHub Actions workflow (`.github/workflows/ci.yml`) for automated testing, code formatting checks, Lambda packaging, and Terraform deployment on pushes to `main`.
- **Development Environment:** Set up the project structure, configured `pyproject.toml` with Poetry for dependency management, and integrated development tools (`black`, `isort`, `flake8`, `pytest`, `moto`, `pre-commit`).

This milestone provides the reliable, low-latency data source required for the subsequent stages of the project.

---

## 🎉 Milestone 2: Message Queue, Deduplication & Labeling Prep (Completed Week 2)

Built upon the ingest pipeline by adding a robust message queue, deduplication, and preparing for the model training phase.

**Key Achievements:**

- **SQS Integration:** Created an SQS FIFO queue (`score-queue.fifo`) with a corresponding Dead Letter Queue (DLQ) using Terraform (`infra/sqs.tf`).
- **Lambda → SQS:** Updated the ingest Lambda's IAM policy (`infra/iam.tf`) and handler code (`src/ingest/handler.py`) to send successfully ingested filing metadata (S3 key, accession no, etc.) as messages to the SQS queue using batching.
- **Deduplication Store:** Provisioned a DynamoDB table (`filing-dedupe`) with TTL enabled for storing processed accession numbers (`infra/dynamodb.tf`).
- **Ingest Deduplication:** Modified the ingest Lambda (`src/ingest/handler.py`) to perform a conditional `PutItem` to the DynamoDB table before processing a filing. If the accession number already exists, the filing is skipped, preventing duplicate processing downstream. Added unit tests (`tests/test_ingest.py`) using `moto` to verify this logic.
- **Monitoring Foundation:** Added CloudWatch alarms (`infra/monitoring.tf`) to monitor the age of the oldest message in the SQS queue, triggering warnings and critical alerts if processing lags.
- **Terraform Refactor:** Created a dedicated S3 bucket for deployment artifacts (`infra/artifacts.tf`) and updated the Lambda definition (`infra/lambda.tf`) to deploy code from this S3 bucket, improving the deployment process.
- **Label Generation Script:** Created the initial script (`src/research/generate_labels.py`) to calculate forward abnormal returns and generate sentiment labels based on price data (`yfinance`) and CIK-ticker mapping (`ticker.txt`). Added necessary dependencies (`pandas`, `yfinance`, etc.) to `pyproject.toml`. (Note: Historical data download via `backfill.py` was completed separately by the user).
- **CI Enhancements:** Updated the GitHub Actions workflow (`.github/workflows/ci.yml`) to run `terraform plan` on pull requests to `main` and to handle uploading the Lambda artifact to S3 during deployment.
- **Completed Backfill downloads 2019-2025 to s3 bucket** 
~1.25 TB of filings (433,921 filings) for 2019 - May 4 2025

```
$ aws s3api list-objects-v2   --bucket edgar-edge-raw   --output json --query "[sum(Contents[].Size), length(Contents[])]"
[
    1374441707718,
    483921
]
```

- **Sampled smaller dataset for efficiency**
Sampled 5% of the filings and got a ~68GB dataset across ~24k objects. 
It turns out the size of the filings is highly skewed. The top filings are over 50MB while filings are typically under 1MB.

Deleted the top 100 largest filings from the sample dataset and the new dataset was ~21GB, a >3x size reduction with only a tiny fraction of the samples removed. 





This milestone ensures that filings are processed reliably and exactly once, and prepares the necessary data labels for the upcoming model fine-tuning stage.

---

## 📅 Roadmap & Milestones

| Week | Engineering deliverable | Research deliverable | KPI Gate |
|------|------------------------|----------------------|----------|
| 1 | Terraform skeleton, SEC RSS PoC → S3 | — | Raw filing in S3 in \<60 s |
| 2 | SQS queue + dedupe; link Lambda → SQS | Label historical filings script | 1‑day ingest of 2023 docs |
| 3 | FastAPI scoring container (dummy model) | DistilRoBERTa fine‑tune notebook | p95 scoring \<300 ms |
| 4 | TorchScript export + fp16 quant | Initial validation F1 score | MVP E2E demo online |
| 5 | Glue crawler, Athena view | Factor builder DAG (daily) | daily parquet table live |
| 6 | Sector/beta neutralisation code | IC computation script | 1‑yr IC ≥0.04 |
| 7 | Vectorbt back‑test notebook | Sharpe, draw‑down report | Sharpe > 0.8 (pre‑cost) |
| 8 | Streamlit dashboard v1 | Publish README + screencast | Public demo URL |
| 9 | Prometheus/Grafana alerts | Walk‑forward robustness tests | p95 ingest lag \<90 s |
| 10 | IR / t‑stat monitoring | Add regime‑shift stress tests | t‑stat ≥3 |
| 11 | Security hardening, load test 100 rps | Final factor correlation matrix | |ρ| \< 0.3 vs F‑F |
| 12 | Documentation polish, white‑paper PDF | Final back‑test w/ txn costs | Cost‑adj Sharpe > 1 |

---

## ⚙️ Configuration & Secrets

- All **non‑sensitive** variables live in `infra/vars.tf` with sensible defaults.
- **Sensitive** values (AWS creds, vendor API keys) are loaded at runtime via:
  - GitHub Actions **Repository Secrets**
  - AWS **Secrets Manager** (pulled by Terraform)
- Provide your own `.tfvars` (see `terraform.tfvars.example`).

---

## 📊 Monitoring & Testing

- **CloudWatch**: ingest lag, SQS age, Lambda errors
- **Prometheus/Grafana**: inference latency histogram on Fargate
- **CD pipeline**: GitHub Actions runs `pytest`, `black --check`, `terraform fmt` on every push

---

## 🤝 Contribution & Acknowledgments

This is primarily a **solo‑dev portfolio project**.  
To suggest improvements or report issues, please open a GitHub Issue or send a PR against this README.

---

## 📜 License

[MIT License](LICENSE)


---

## Next Steps For Production Deployment
- switch from lambda + RSS feed to container + PDS feed for sub-second prod latency

----
