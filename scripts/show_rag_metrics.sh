#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="${PROJECT_NAME:-hospital-agentic-rag}"
ARTIFACT_BUCKET="${ARTIFACT_BUCKET:-mlopswithsagemaker111}"
AWS_REGION="${AWS_REGION:-us-west-1}"
NAMESPACE="${RAG_METRICS_NAMESPACE:-${PROJECT_NAME}/RAG}"
METRIC_NAME="${1:-OverallAgenticRagScore}"

echo "Latest metrics artifact:"
aws s3 cp "s3://${ARTIFACT_BUCKET}/${PROJECT_NAME}/metrics/latest-rag-metrics.json" - --region "${AWS_REGION}" \
  | python -m json.tool

echo
echo "CloudWatch ${METRIC_NAME} datapoints:"
aws cloudwatch get-metric-statistics \
  --region "${AWS_REGION}" \
  --namespace "${NAMESPACE}" \
  --metric-name "${METRIC_NAME}" \
  --dimensions "Name=ProjectName,Value=${PROJECT_NAME}" \
  --statistics Average Maximum \
  --period 300 \
  --start-time "$(date -u -d '2 hours ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
