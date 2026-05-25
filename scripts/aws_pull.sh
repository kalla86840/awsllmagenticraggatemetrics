#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARAMS_FILE="${ROOT_DIR}/infrastructure/codepipeline-parameters.example.env"

if [[ -f "${PARAMS_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${PARAMS_FILE}"
fi

PROJECT_NAME="${PROJECT_NAME:-awsllmagenticraggatemetrics}"
ARTIFACT_BUCKET="${ARTIFACT_BUCKET:-mlopswithsagemaker111}"
AWS_REGION="${AWS_REGION:-us-west-1}"
METRIC_NAME="${1:-OverallAgenticRagScore}"
METRICS_NAMESPACE="${PROJECT_NAME}/RAG"

echo "Using AWS identity:"
aws sts get-caller-identity --region "${AWS_REGION}"

echo
echo "Pipeline state:"
aws codepipeline get-pipeline-state \
  --region "${AWS_REGION}" \
  --name "${PROJECT_NAME}" \
  --query "stageStates[].{stage:stageName,status:latestExecution.status,run:latestExecution.pipelineExecutionId}" \
  --output table

echo
echo "Endpoint stack outputs:"
aws cloudformation describe-stacks \
  --region "${AWS_REGION}" \
  --stack-name "${PROJECT_NAME}-endpoint" \
  --query "Stacks[0].Outputs[].{key:OutputKey,value:OutputValue}" \
  --output table || true

echo
echo "Latest RAG metrics artifact:"
aws s3 cp "s3://${ARTIFACT_BUCKET}/${PROJECT_NAME}/metrics/latest-rag-metrics.json" - \
  --region "${AWS_REGION}" \
  | python -m json.tool || true

echo
echo "Recent CloudWatch ${METRIC_NAME} datapoints:"
aws cloudwatch get-metric-statistics \
  --region "${AWS_REGION}" \
  --namespace "${METRICS_NAMESPACE}" \
  --metric-name "${METRIC_NAME}" \
  --dimensions "Name=ProjectName,Value=${PROJECT_NAME}" \
  --statistics Average Maximum \
  --period 300 \
  --start-time "$(date -u -d '2 hours ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --output table || true
