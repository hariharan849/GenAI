#!/bin/bash

# Kill any existing processes on these ports
echo "Stopping any existing processes on ports 8000-8004..."
lsof -ti:8000,8001,8002,8003,8004 | xargs kill -9 2>/dev/null

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# Set common environment variables for local development
export GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project)
export GOOGLE_CLOUD_LOCATION="global"
export GOOGLE_GENAI_USE_VERTEXAI="True" # Use Gemini API locally
export GOOGLE_API_KEY="<your-key-here>" # Use if not using Vertex AI
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export AWS_REGION="${AWS_REGION:-us-east-1}"
export BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-amazon.nova-micro-v1:0}"
export SOURCE_INTELLIGENCE_TRANSPORT="stdio"
export JUDGE_DEFAULT_PASS="${JUDGE_DEFAULT_PASS:-true}"
export SOURCE_INTELLIGENCE_STDIO_COMMAND="uv"
export SOURCE_INTELLIGENCE_STDIO_ARGS="[\"run\", \"--project\", \"${SCRIPT_DIR}/agents/source_intelligence\", \"python\", \"${SCRIPT_DIR}/agents/source_intelligence/main.py\", \"--stdio\"]"

echo "Starting Researcher Agent on port 8001..."
pushd agents/researcher
uv run python main.py &
RESEARCHER_PID=$!
popd

echo "Starting Judge Agent on port 8002..."
pushd agents/judge
PORT=8002 A2A_PUBLIC_URL=http://localhost:8002 uv run main.py &
JUDGE_PID=$!
popd

echo "Starting Content Builder Agent on port 8003..."
pushd agents/content_builder
PORT=8003 A2A_PUBLIC_URL=http://localhost:8003 uv run python main.py &
CONTENT_BUILDER_PID=$!
popd

export RESEARCHER_AGENT_CARD_URL=http://localhost:8001/a2a/agent/.well-known/agent-card.json
export JUDGE_AGENT_CARD_URL=http://localhost:8002/a2a/agent/.well-known/agent-card.json
export CONTENT_BUILDER_AGENT_CARD_URL=http://localhost:8003/a2a/agent/.well-known/agent-card.json

echo "Starting Orchestrator Agent on port 8004..."
pushd agents/orchestrator
uv run python main.py &
ORCHESTRATOR_PID=$!
popd

# Wait a bit for them to start up
sleep 5

echo "Starting App Server on port 8000..."
pushd app
export AGENT_SERVER_URL=http://localhost:8004

uv run uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
popd

echo "All agents started!"
echo "Source Intelligence MCP: stdio (one local process per agent)"
echo "Researcher: http://localhost:8001"
echo "Judge: http://localhost:8002"
echo "Content Builder: http://localhost:8003"
echo "Orchestrator: http://localhost:8004"
echo "App Server (Frontend): http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop all agents."

# Wait for all processes
trap "kill $RESEARCHER_PID $JUDGE_PID $CONTENT_BUILDER_PID $ORCHESTRATOR_PID $BACKEND_PID; exit" INT
wait
