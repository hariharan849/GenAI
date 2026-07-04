#!/usr/bin/env bash
# Generate API traffic for Grafana/Prometheus dashboard panels.
# Press Ctrl+C to stop.

set -u

BASE_URL="${BASE_URL:-http://localhost:8083}"
COUNT="${1:-${COUNT:-100}}"
SLEEP_SECONDS="${SLEEP_SECONDS:-0.3}"
ENABLE_RAG="${ENABLE_RAG:-0}"

QUERIES=(
  "How do I use the Blur node in Nuke?"
  "What is the Merge node used for?"
  "How do I read EXR files in Nuke?"
  "How can I stabilize footage?"
)

request() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local code

  if [[ -n "$body" ]]; then
    code=$(curl -s -o /dev/null -w "%{http_code}" \
      -X "$method" \
      -H "Content-Type: application/json" \
      --data "$body" \
      "${BASE_URL}${path}")
  else
    code=$(curl -s -o /dev/null -w "%{http_code}" \
      -X "$method" \
      "${BASE_URL}${path}")
  fi

  printf '[%s] %-4s %-28s -> HTTP %s\n' "$(date '+%H:%M:%S')" "$method" "$path" "$code"
}

echo "Generating ${COUNT} dashboard test requests against ${BASE_URL}"
echo "Set ENABLE_RAG=1 to include /ask calls. Current ENABLE_RAG=${ENABLE_RAG}"

for i in $(seq 1 "$COUNT"); do
  query="${QUERIES[$(( (i - 1) % ${#QUERIES[@]} ))]}"

  case $(( i % 6 )) in
    0)
      request "GET" "/api/v1/health"
      ;;
    1)
      request "POST" "/api/v1/hybrid-search/" \
        "{\"query\":\"${query}\",\"size\":3,\"use_hybrid\":false,\"knowledge_source\":\"nuke\"}"
      ;;
    2)
      request "POST" "/api/v1/hybrid-search/" \
        "{\"query\":\"\",\"size\":3,\"use_hybrid\":false,\"knowledge_source\":\"nuke\"}"
      ;;
    3)
      request "GET" "/api/v1/not-found-${i}"
      ;;
    4)
      request "POST" "/api/v1/feedback" \
        "{\"trace_id\":\"dashboard-test-${i}\",\"score\":2,\"comment\":\"intentional validation error\"}"
      ;;
    *)
      if [[ "$ENABLE_RAG" == "1" ]]; then
        request "POST" "/api/v1/ask" \
          "{\"query\":\"${query}\",\"top_k\":2,\"use_hybrid\":false,\"model\":\"llama3.2:1b\",\"knowledge_source\":\"nuke\"}"
      else
        request "GET" "/metrics"
      fi
      ;;
  esac

  sleep "$SLEEP_SECONDS"
done
