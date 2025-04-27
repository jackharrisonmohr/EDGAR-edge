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

## 📅 Roadmap & Milestones

| Week | Deliverable                             | KPI Gate                                |
|------|-----------------------------------------|-----------------------------------------|
| 1    | Lambda ingest PoC → S3 < 60 s           | Raw filing appears in S3 < 60 s         |
| 2    | SQS dedupe + historical downloader      | 2023 filings laid down in one day       |
| 3    | FastAPI scoring (dummy model)           | p95 < 300 ms                            |
| 4    | TorchScript export + fp16 quantisation  | E2E demo online                         |
| …    | …                                       | …                                       |
| 12   | White‑paper PDF + full back‑test        | Cost‑adjusted Sharpe > 1                |

See [roadmap.md](docs/roadmap.md) for full detail.
Also see the [project board] (https://github.com/users/jackharrisonmohr/projects/1/views/1) for current issues.

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