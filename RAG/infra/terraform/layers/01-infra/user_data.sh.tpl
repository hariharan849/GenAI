#!/bin/bash
set -e
exec > /var/log/rag-init.log 2>&1
trap 'echo "ERROR: user_data failed at line $LINENO — check /var/log/rag-init.log" | tee /home/ubuntu/FAILED >&2' ERR

echo "=== RAG infra bootstrap starting ==="
date

# System dependencies
apt-get update -y
apt-get install -y docker.io docker-compose-plugin awscli git curl

systemctl start docker
systemctl enable docker
usermod -aG docker ubuntu

# OpenSearch requirement: vm.max_map_count
sysctl -w vm.max_map_count=262144
echo "vm.max_map_count=262144" >> /etc/sysctl.conf

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

echo "=== Starting infra services (profile: ${orchestrator_profile}) ==="
docker compose -f docker-compose.infra.yaml \
  --profile "${orchestrator_profile}" \
  up -d \
  || { echo "COMPOSE UP FAILED" >> /home/ubuntu/FAILED; exit 1; }

echo "=== Bootstrap complete ==="
date
touch /home/ubuntu/READY
