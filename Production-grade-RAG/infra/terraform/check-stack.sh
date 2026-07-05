#!/usr/bin/env bash
# Smoke test for the full stack after deployment.
# Usage: ./check-stack.sh <alb_dns_name>
#
# Example:
#   ALB=$(cd layers/04-endpoints && terraform output -raw alb_dns_name)
#   ./check-stack.sh $ALB

set -euo pipefail

ALB="${1:-}"
if [[ -z "$ALB" ]]; then
  echo "Usage: $0 <alb_dns_name>"
  echo "  Get it with: cd layers/04-endpoints && terraform output -raw alb_dns_name"
  exit 1
fi

PASS=0
FAIL=0

check() {
  local label="$1"
  local url="$2"
  local expected_code="${3:-200}"

  actual=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")
  if [[ "$actual" == "$expected_code" ]]; then
    echo "  PASS  $label ($url)"
    (( PASS++ )) || true
  else
    echo "  FAIL  $label ($url) — expected $expected_code, got $actual"
    (( FAIL++ )) || true
  fi
}

echo ""
echo "=== Nuke RAG Stack Smoke Test ==="
echo "ALB: http://$ALB"
echo ""

echo "-- ALB routing --"
check "UI root"              "http://$ALB/"                200
check "API health"           "http://$ALB/api/v1/health"  200
check "API hybrid-search"   "http://$ALB/api/v1/hybrid-search/" 405  # POST-only endpoint returns 405 on GET

echo ""
echo "-- Results --"
echo "  PASS: $PASS"
echo "  FAIL: $FAIL"
echo ""

if [[ $FAIL -gt 0 ]]; then
  echo "Stack is NOT fully healthy. Check /var/log/rag-init.log on the failing EC2."
  exit 1
else
  echo "All checks passed. Stack is healthy."
fi
