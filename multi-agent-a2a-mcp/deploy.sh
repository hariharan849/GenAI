#!/bin/bash

set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "${SCRIPT_DIR}"

if [ -f ".env" ]; then
  source .env
fi

if [[ "${GOOGLE_CLOUD_PROJECT}" == "" ]]; then
  GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project -q)
fi
if [[ "${GEMINI_API_KEY}" == "" ]]; then
  echo "ERROR: Set GEMINI_API_KEY in .env before deploying the researcher service."
  exit 1
fi
if [[ "${GOOGLE_CLOUD_PROJECT}" == "" ]]; then
  echo "ERROR: Run 'gcloud config set project' command to set active project, or set GOOGLE_CLOUD_PROJECT environment variable."
  exit 1
fi

REGION="${GOOGLE_CLOUD_LOCATION}"
if [[ "${REGION}" == "global" ]]; then
  echo "GOOGLE_CLOUD_LOCATION is set to 'global'. Getting a default location for Cloud Run."
  REGION=""
fi

if [[ "${REGION}" == "" ]]; then
  REGION=$(gcloud config get-value compute/region -q)
  if [[ "${REGION}" == "" ]]; then
    REGION="us-central1"
    echo "WARNING: Cannot get a configured compute region. Defaulting to ${REGION}."
  fi
fi
echo "Using project ${GOOGLE_CLOUD_PROJECT}."
echo "Using compute region ${REGION}."

gcloud run deploy source-intelligence \
  --source agents/source_intelligence \
  --project $GOOGLE_CLOUD_PROJECT \
  --region $REGION \
  --no-allow-unauthenticated \
  --set-secrets TAVILY_API_KEY=tavily-api-key:latest
SOURCE_INTELLIGENCE_URL=$(gcloud run services describe source-intelligence --region $REGION --format='value(status.url)')

gcloud run deploy researcher \
  --source agents/researcher \
  --project $GOOGLE_CLOUD_PROJECT \
  --region $REGION \
  --max-instances 1 \
  --no-allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT}" \
  --set-env-vars GEMINI_API_KEY="${GEMINI_API_KEY}"
RESEARCHER_URL=$(gcloud run services describe researcher --region $REGION --format='value(status.url)')
gcloud run services update researcher \
  --project $GOOGLE_CLOUD_PROJECT \
  --region $REGION \
  --update-env-vars A2A_PUBLIC_URL=$RESEARCHER_URL,SOURCE_INTELLIGENCE_TRANSPORT=http,SOURCE_INTELLIGENCE_URL=$SOURCE_INTELLIGENCE_URL/mcp,SOURCE_INTELLIGENCE_AUDIENCE=$SOURCE_INTELLIGENCE_URL

gcloud run deploy content-builder \
  --source agents/content_builder \
  --project $GOOGLE_CLOUD_PROJECT \
  --region $REGION \
  --no-allow-unauthenticated \
  --set-secrets ANTHROPIC_API_KEY=anthropic-api-key:latest \
  --set-env-vars CLAUDE_MODEL="claude-sonnet-4-20250514",CLAUDE_MAX_TOKENS="4096",CLAUDE_TIMEOUT_SECONDS="60"
CONTENT_BUILDER_URL=$(gcloud run services describe content-builder --region $REGION --format='value(status.url)')
gcloud run services update content-builder \
  --project $GOOGLE_CLOUD_PROJECT \
  --region $REGION \
  --update-env-vars A2A_PUBLIC_URL=$CONTENT_BUILDER_URL,SOURCE_INTELLIGENCE_TRANSPORT=http,SOURCE_INTELLIGENCE_URL=$SOURCE_INTELLIGENCE_URL/mcp,SOURCE_INTELLIGENCE_AUDIENCE=$SOURCE_INTELLIGENCE_URL

gcloud run deploy judge \
  --source agents/judge \
  --project $GOOGLE_CLOUD_PROJECT \
  --region $REGION \
  --no-allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT}" \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI="true"
JUDGE_URL=$(gcloud run services describe judge --region $REGION --format='value(status.url)')
gcloud run services update judge \
  --project $GOOGLE_CLOUD_PROJECT \
  --region $REGION \
  --update-env-vars A2A_PUBLIC_URL=$JUDGE_URL,SOURCE_INTELLIGENCE_TRANSPORT=http,SOURCE_INTELLIGENCE_URL=$SOURCE_INTELLIGENCE_URL/mcp,SOURCE_INTELLIGENCE_AUDIENCE=$SOURCE_INTELLIGENCE_URL

for SERVICE in researcher judge content-builder; do
  SERVICE_ACCOUNT=$(gcloud run services describe $SERVICE --project $GOOGLE_CLOUD_PROJECT --region $REGION --format='value(spec.template.spec.serviceAccountName)')
  if [[ "$SERVICE_ACCOUNT" == "" ]]; then
    PROJECT_NUMBER=$(gcloud projects describe $GOOGLE_CLOUD_PROJECT --format='value(projectNumber)')
    SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
  fi
  gcloud run services add-iam-policy-binding source-intelligence \
    --project $GOOGLE_CLOUD_PROJECT \
    --region $REGION \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role=roles/run.invoker
done

gcloud run deploy orchestrator \
  --source agents/orchestrator \
  --project $GOOGLE_CLOUD_PROJECT \
  --region $REGION \
  --max-instances 1 \
  --no-allow-unauthenticated \
  --set-env-vars RESEARCHER_AGENT_CARD_URL=$RESEARCHER_URL/a2a/agent/.well-known/agent-card.json \
  --set-env-vars JUDGE_AGENT_CARD_URL=$JUDGE_URL/a2a/agent/.well-known/agent-card.json \
  --set-env-vars CONTENT_BUILDER_AGENT_CARD_URL=$CONTENT_BUILDER_URL/a2a/agent/.well-known/agent-card.json \
  --set-env-vars GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT}" \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI="true"
ORCHESTRATOR_URL=$(gcloud run services describe orchestrator --region $REGION --format='value(status.url)')

gcloud run deploy course-creator \
  --source app \
  --project $GOOGLE_CLOUD_PROJECT \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars AGENT_SERVER_URL=$ORCHESTRATOR_URL \
  --set-env-vars GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT}"
