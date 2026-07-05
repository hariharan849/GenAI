#!/bin/bash
set -e
exec > /var/log/rag-init.log 2>&1
trap 'echo "ERROR: user_data failed at line $LINENO — check /var/log/rag-init.log" | tee /home/ubuntu/FAILED >&2' ERR

echo "=== RAG ui bootstrap starting ==="
date

# System dependencies
apt-get update -y
apt-get install -y docker.io docker-compose-plugin awscli git curl

systemctl start docker
systemctl enable docker
usermod -aG docker ubuntu

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

# API_HOST persists across reboots via /etc/environment
echo "API_HOST=${api_private_ip}" >> /etc/environment
export API_HOST="${api_private_ip}"

echo "=== Building ui container ==="
docker compose -f docker-compose.ui.yaml build ui \
  || { echo "BUILD FAILED" >> /home/ubuntu/FAILED; exit 1; }

echo "=== Starting ui service ==="
docker compose -f docker-compose.ui.yaml up -d \
  || { echo "COMPOSE UP FAILED" >> /home/ubuntu/FAILED; exit 1; }

echo "=== Bootstrap complete ==="
date
touch /home/ubuntu/READY
