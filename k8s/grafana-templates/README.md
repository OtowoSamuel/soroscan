# SoroScan Grafana Dashboard Templates

This folder contains reusable Grafana dashboard JSON templates for common monitoring scenarios.

## Templates

- `system-health-overview.json`: service uptime, error rates, queue pressure, and resource health.
- `event-ingestion-metrics.json`: ingestion throughput, lag, deduplication, and error tracking.
- `webhook-delivery-status.json`: delivery success rate, retries, response latency, and failure diagnostics.
- `performance-analysis.json`: API latency percentiles, DB query performance, and worker runtime analysis.

## Template Features

- Multi-instance dashboard variables: datasource, namespace, job, and instance.
- Deployment annotations for timeline correlation.
- Exportable JSON dashboards for easy sharing/importing.

## Usage

1. Open Grafana and navigate to **Dashboards -> New -> Import**.
2. Upload one of the JSON files in this folder.
3. Select your Prometheus datasource when prompted.
4. Adjust variable defaults (`namespace`, `job`, `instance`) for your environment.
