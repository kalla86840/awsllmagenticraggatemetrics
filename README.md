# Hospital Agentic RAG CodePipeline

This package creates an AWS CI/CD pipeline for an OpenAI-backed agentic RAG endpoint. The RAG knowledge source is a text manual at `src/hospital_operations_manual.txt`.

Agents:

- Agent 1: `hospital` handles hospital operations, routing, bed placement, staffing, and escalation coordination.
- Agent 2: `doctor` handles clinical risk review and escalation considerations.
- Agent 3: `nurse` handles bedside handoff, monitoring, and documentation priorities.

## Flow

```text
GitHub
  -> AWS CodePipeline
  -> AgenticRagGate CodeBuild stage
  -> pytest, retrieval metrics, agent routing metrics, citation metrics
  -> low temporary quality gate, default 0.25
  -> Deploy CodeBuild stage
  -> package Lambda artifact
  -> upload artifact to S3
  -> CloudFormation deploys Lambda Function URL
  -> Lambda retrieves manual sections
  -> OpenAI Responses API runs hospital, doctor, and nurse agents
  -> final structured care-coordination response
```

The implementation uses the OpenAI Responses API with structured JSON outputs. OpenAI recommends Responses for new agentic applications, and file/retrieval-style workflows can be grounded through retrieved context or OpenAI file search depending on the architecture. The AWS side uses CodePipeline with a CodeBuild action and CloudFormation deployment.

## Local Test

```bash
cd hospital-agentic-rag-codepipeline
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests
python scripts/evaluate_rag.py --min-score 0.25 --output dist/rag-metrics.json
```

Invoke locally without calling OpenAI:

```bash
set APP_MODE=local
python -c "import json; from src.app import lambda_handler; event={'body': open('samples/hospital_event.json').read()}; print(lambda_handler(event, None)['body'])"
```

## OpenAI Secret

Store the API key in AWS Secrets Manager:

```bash
aws secretsmanager create-secret \
  --region us-west-1 \
  --name openai/api-key \
  --secret-string "${OPENAI_API_KEY_VALUE}"
```

Pass that secret ARN to the CodePipeline stack as `OpenAIApiKeySecretArn`.

This project is already filled with the current default AWS values:

- AWS region: `us-west-1`
- AWS account: `659613508664`
- Artifact bucket: `mlopswithsagemaker111`
- CodeConnections ARN: `arn:aws:codeconnections:us-west-1:659613508664:connection/4ea8863c-728d-450a-8752-251946939b36`
- OpenAI secret ARN: `arn:aws:secretsmanager:us-west-1:659613508664:secret:openai/api-key-6BGXhJ`
- GitHub repository: `kalla86840/awsllmagenticrag`
- Branch: `main`
- RAG metrics namespace: `hospital-agentic-rag/RAG`, derived from `ProjectName`

The same values are also saved in `infrastructure/codepipeline-parameters.example.json`, `infrastructure/codepipeline-parameters.example.env`, and `.env.example`.

## Deploy CodePipeline

```bash
aws cloudformation deploy \
  --region us-west-1 \
  --template-file hospital-agentic-rag-codepipeline/infrastructure/codepipeline.yaml \
  --stack-name hospital-agentic-rag-cicd \
  --capabilities CAPABILITY_NAMED_IAM
```

The template defaults are already filled in. To override explicitly from bash, source the env example and pass the values:

```bash
source hospital-agentic-rag-codepipeline/infrastructure/codepipeline-parameters.example.env

aws cloudformation deploy \
  --region "${AWS_REGION}" \
  --template-file hospital-agentic-rag-codepipeline/infrastructure/codepipeline.yaml \
  --stack-name hospital-agentic-rag-cicd \
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
```

After deployment, read the endpoint URL from the `hospital-agentic-rag-endpoint` CloudFormation stack output named `FunctionUrl`.

## RAG Performance

`scripts/evaluate_rag.py` checks whether the manual retrieves the expected section for chest pain, sepsis, stroke, and nurse handoff prompts. It also runs local agentic RAG cases to confirm Agent 1 `hospital`, Agent 2 `doctor`, and Agent 3 `nurse` are routed, cite retrieved manual sections, and produce the expected escalation level.

```bash
python scripts/evaluate_rag.py --min-score 0.25 --output dist/rag-metrics.json
```

The default gate is intentionally low for now: `RAG_GATE_MIN_SCORE=0.25`. Raise `RagGateMinScore` in `infrastructure/codepipeline.yaml` or pass it as a CloudFormation parameter once your baseline looks stable.

The build publishes metrics to:

- S3 JSON artifact: `s3://$ARTIFACT_BUCKET/$PROJECT_NAME/metrics/latest-rag-metrics.json`
- CloudWatch metrics under namespace `hospital-agentic-rag/RAG`: `RagRetrievalScore`, `AgenticRagScore`, and `OverallAgenticRagScore`

View the metrics from a bash shell:

```bash
export PROJECT_NAME=hospital-agentic-rag
export ARTIFACT_BUCKET=mlopswithsagemaker111
export AWS_REGION=us-west-1

bash scripts/show_rag_metrics.sh
bash scripts/show_rag_metrics.sh RagRetrievalScore
bash scripts/show_rag_metrics.sh AgenticRagScore
```

Direct AWS CLI equivalents:

```bash
aws s3 cp "s3://${ARTIFACT_BUCKET}/${PROJECT_NAME}/metrics/latest-rag-metrics.json" - | python -m json.tool

aws cloudwatch get-metric-statistics \
  --region "${AWS_REGION}" \
  --namespace "${PROJECT_NAME}/RAG" \
  --metric-name OverallAgenticRagScore \
  --dimensions "Name=ProjectName,Value=${PROJECT_NAME}" \
  --start-time "$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 3600 \
  --statistics Average Maximum \
  --output table
```

## References

- [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses/create?api-mode=responses)
- [OpenAI Responses migration guide](https://platform.openai.com/docs/guides/responses-vs-chat-completions)
- [OpenAI file search guide](https://platform.openai.com/docs/guides/tools-file-search/)
- [AWS CodePipeline CodeBuild action reference](https://docs.aws.amazon.com/codepipeline/latest/userguide/action-reference-CodeBuild.html)
