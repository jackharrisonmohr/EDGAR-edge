# Architecture

This document expands on the high-level flow in `README.md`, describing each component in more detail and illustrating dependencies.

```
    ┌────────────────────────┐
    │      RSS / API Feed    │
    │(EDGAR RSS or vendor)   │
    └────────────┬───────────┘
                 │
                 ▼
    ┌───────────────────────┐         ┌──────────────────────┐
    │   Ingest Lambda       │────────▶│ S3 `raw/`            │
    │ (Python 3.11 on AWS)  │         │(versioned, encrypted)│
    └────────┬──────────────┘         └──────────────────────┘
             │     │
             │     ▼
             │    ┌────────────────┐
             │    │CloudWatch Logs │
             │    │ & Metrics      │
             │    └────────────────┘
             │
             ▼
    ┌────────────────────────┐         ┌──────────────────────┐
    │    SQS FIFO Queue      │────────▶│ Fargate Scoring      │
    │ (dedupe, ordering)     │         │ (FastAPI+TorchScript)|
    └────────┬───────────────┘         └─────────┬────────────┘
             │                                   │
             │                                   ▼
             │                        ┌──────────────────────┐
             │                        │ S3 `scored/`         │
             │                        │ (JSON blobs)         │
             │                        └──────────────────────┘
             ▼
    ┌────────────────────────┐
    │ Athena / Glue Catalog  │
    │ (Parquet schema)       │
    └────────────────────────┘
             │
             ▼
    ┌────────────────────────┐         ┌──────────────────────┐
    │Airflow Factor Builder  │────────▶│ S3 `factors/` + PDF  │
    │ (ECS Cron DAG)         │         │ reports              │
    └────────┬───────────────┘         └──────────────────────┘
             │
             ▼
    ┌────────────────────────┐
    │ Streamlit Dashboard    │
    │ (ECS Fargate service)  │
    └────────┬───────────────┘
             │
             ▼
    ┌────────────────────────┐
    │ Grafana / Prometheus   │
    │ (Latency, uptime)      │
    └────────────────────────┘
```

## Component Details

- **RSS / API Feed**:  
  - *Free PoC*: SEC RSS endpoints (`getcurrent&type=8-K/10-K`).  
  - *Prod*: vendor WebSocket or SEC Public Dissemination Service (PDS).

- **Ingest Lambda**:  
  - Language: Python 3.11.  
  - Responsibilities: poll feed, dedupe in-memory, write new filings to S3 `raw/`, emit metrics.

- **S3 `raw/`**:  
  - Stores raw JSON of each filing.  
  - Versioning on; server-side AES-256 encryption.  
  - Partitioned by date and form type (`raw/{yyyy}/{mm}/{form}/accNo.json`).

- **CloudWatch Logs & Metrics**:  
  - Captures ingest lag (`LAG_SECS`), Lambda errors, invocation count.  
  - Enables metric alarms for high lag or errors.

- **SQS FIFO Queue**:  
  - Ensures ordered, deduplicated delivery to scoring stage.  
  - Decouples ingest spikes from downstream processing.

- **Fargate Scoring**:  
  - Container: FastAPI + TorchScript model.  
  - Autoscaled ECS service; p95 inference < 200 ms.  
  - Publishes JSON to S3 `scored/` with raw score, z-score, latency, model version.

- **S3 `scored/`**:  
  - Stores scoring outputs partitioned by date.  
  - Schema tracked in Athena / Glue Catalog for querying.

- **Athena / Glue Catalog**:  
  - Defines table over Parquet on S3.  
  - Enables SQL queries for factor builder and ad-hoc analysis.

- **Airflow Factor Builder**:  
  - Scheduled via ECS Cron on Fargate.  
  - Runs Python DAG to compute cross-sectional z-scores, neutralisation, back-test metrics, writes Parquet & PDF.

- **S3 `factors/` + PDF reports**:  
  - Daily Parquet store of factor values.  
  - Versioned PDF summary in `reports/`.

- **Streamlit Dashboard**:  
  - ECS Fargate service exposing interactive UI.  
  - Reads latest factors from S3 + Redis (for latest intraday sentiment).

- **Grafana / Prometheus**:  
  - Sidecar on Fargate collects latency histograms.  
  - Dashboards track ingest lag, queue depth, inference p95, factor build time.

---

