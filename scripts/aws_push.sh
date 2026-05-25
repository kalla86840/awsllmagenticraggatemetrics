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
CODESTAR_CONNECTION_ARN="${CODESTAR_CONNECTION_ARN:-arn:aws:codeconnections:us-west-1:659613508664:connection/4ea8863c-728d-450a-8752-251946939b36}"
REPOSITORY_ID="${REPOSITORY_ID:-kalla86840/awsllmagenticraggatemetrics}"
BRANCH_NAME="${BRANCH_NAME:-main}"
OPENAI_API_KEY_SECRET_ARN="${OPENAI_API_KEY_SECRET_ARN:-arn:aws:secretsmanager:us-west-1:659613508664:secret:openai/api-key-6BGXhJ}"
OPENAI_MODEL="${OPENAI_MODEL:-gpt-5.2}"
RAG_GATE_MIN_SCORE="${RAG_GATE_MIN_SCORE:-0.25}"

echo "Using AWS identity:"
aws sts get-caller-identity --region "${AWS_REGION}"

echo
echo "Deploying CodePipeline stack ${PROJECT_NAME}-cicd in ${AWS_REGION}..."
aws cloudformation deploy \
  --region "${AWS_REGION}" \
  --template-file "${ROOT_DIR}/infrastructure/codepipeline.yaml" \
  --stack-name "${PROJECT_NAME}-cicd" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ProjectName="${PROJECT_NAME}" \
    ArtifactBucketName="${ARTIFACT_BUCKET}" \
    CodeStarConnectionArn="${CODESTAR_CONNECTION_ARN}" \
    RepositoryId="${REPOSITORY_ID}" \
    BranchName="${BRANCH_NAME}" \
    OpenAIApiKeySecretArn="${OPENAI_API_KEY_SECRET_ARN}" \
    OpenAIModel="${OPENAI_MODEL}" \
    RagGateMinScore="${RAG_GATE_MIN_SCORE}"

echo
echo "Starting pipeline execution..."
aws codepipeline start-pipeline-execution \
  --region "${AWS_REGION}" \
  --name "${PROJECT_NAME}"

echo
echo "Push complete. Run bash scripts/aws_pull.sh to pull status, endpoint outputs, and metrics."
