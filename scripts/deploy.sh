#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Checking required CLI tools..."
command -v aws >/dev/null 2>&1 || {
  echo "aws CLI is required. Install it first: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html" >&2
  exit 127
}

echo
echo "Deploying AWS CodePipeline and starting the RAG CI/CD run..."
bash "${ROOT_DIR}/scripts/aws_push.sh"

echo
echo "Deployment started. Pull current AWS status with:"
echo "  bash scripts/aws_pull.sh"
