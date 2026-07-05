#!/bin/bash
set -e
exec > /var/log/rag-init.log 2>&1
trap 'echo "ERROR: user_data failed at line $LINENO — check /var/log/rag-init.log" | tee /home/ubuntu/FAILED >&2' ERR

echo "=== RAG api bootstrap starting ==="
date

# System dependencies
apt-get update -y
apt-get install -y docker.io docker-compose-plugin awscli git curl

systemctl start docker
systemctl enable docker
usermod -aG docker ubuntu

# Install Ollama (runs on host, not in Docker)
echo "=== Installing Ollama ==="
curl -fsSL https://ollama.com/install.sh | sh
systemctl enable ollama
systemctl start ollama

# Wait for Ollama to be ready (cold start can take 10-15s)
echo "=== Waiting for Ollama to be ready ==="
until ollama list >/dev/null 2>&1; do
  echo "  ollama not ready yet, waiting 2s..."
  sleep 2
done
echo "Ollama ready"

# Pull the model (llama3.2:1b ~ 1.3 GB — takes 3-5 min on first run)
echo "=== Pulling llama3.2:1b ==="
ollama pull llama3.2:1b || {
  echo "First pull attempt failed, retrying..."
  sleep 5
  ollama pull llama3.2:1b
}

echo "=== Cloning repo ==="
cd /home/ubuntu

%{ if github_pat_ssm_name != "" ~}
GITHUB_PAT=$(aws ssm get-parameter \
  --name "${github_pat_ssm_name}" \
  --with-decryption \
  --region "${aws_region}" \
  --query Parameter.Value \
  --output text)
git clone "https://$${GITHUB_PAT}@github.com/${github_owner}/${github_repo}.git" rag
%{ else ~}
git clone "https://github.com/${github_owner}/${github_repo}.git" rag
%{ endif ~}

cd rag/RAG

echo "=== Pulling .env from SSM ==="
aws ssm get-parameter \
  --name "${env_ssm_name}" \
  --with-decryption \
  --region "${aws_region}" \
  --query Parameter.Value \
  --output text > .env
chmod 600 .env

# INFRA_HOST persists across reboots via /etc/environment
echo "INFRA_HOST=${infra_private_ip}" >> /etc/environment
export INFRA_HOST="${infra_private_ip}"

echo "=== Building api container ==="
docker compose -f docker-compose.api.yaml build api \
  || { echo "BUILD FAILED" >> /home/ubuntu/FAILED; exit 1; }

echo "=== Starting api service ==="
docker compose -f docker-compose.api.yaml up -d \
  || { echo "COMPOSE UP FAILED" >> /home/ubuntu/FAILED; exit 1; }

echo "=== Bootstrap complete ==="
date
touch /home/ubuntu/READY
