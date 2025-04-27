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