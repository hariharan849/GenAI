# Terraform Infrastructure — Nuke RAG Stack

Four independently deployable layers on AWS.
Deploy order is strict. Each layer reads the previous layer's outputs from S3 remote state.

```
bootstrap → 01-infra → 02-api → 03-ui → 04-endpoints
```

**Estimated monthly cost:** ~$228 on-demand / ~$95 with 1-year Reserved Instances.

---

## Prerequisites

- Terraform >= 1.6 (`brew install terraform` or https://developer.hashicorp.com/terraform/install)
- AWS CLI configured (`aws configure`) with an IAM user that has EC2/S3/DynamoDB/IAM/ELB permissions
- SSH key pair: `ssh-keygen -t rsa -b 4096 -f ~/.ssh/rag-key`
- Your public IP: `curl -s https://checkip.amazonaws.com` — used as `admin_cidr`

---

## Step 0 — Seed SSM secrets (once)

Before any `terraform apply`, put your `.env` contents into SSM:

```bash
aws ssm put-parameter \
  --name "/rag/env" \
  --value "$(cat .env)" \
  --type SecureString \
  --region us-east-1
```

Verify: `aws ssm get-parameter --name "/rag/env" --with-decryption --query Parameter.Value --output text | head -3`

---

## Step 1 — Bootstrap (once)

```bash
cd infra/terraform/bootstrap
terraform init
terraform apply
# Copy the state_bucket_name output value
```

**Copy the bucket name** (e.g., `rag-terraform-state-a1b2c3d4`) into all four `backend.tf` files,
replacing `REPLACE_WITH_BUCKET_NAME`. Also copy to each `terraform.tfvars` as `state_bucket`.

Commit `bootstrap/terraform.tfstate` to git — it contains only resource IDs, no secrets.
This is the only state file you commit; never commit `layers/*/terraform.tfstate`.

---

## Step 2 — Configure each layer

Copy each layer's `terraform.tfvars.example` to `terraform.tfvars` and fill in your values:

```bash
for layer in layers/01-infra layers/02-api layers/03-ui layers/04-endpoints; do
  cp $layer/terraform.tfvars.example $layer/terraform.tfvars
done
```

Required values in each `terraform.tfvars`:
- `admin_cidr` — your IP as `x.x.x.x/32`
- `public_key_content` — contents of `~/.ssh/rag-key.pub`
- `github_owner` — your GitHub username
- `state_bucket` — the bucket name from Step 1

---

## Step 3 — Split docker-compose (code change)

The Terraform user_data scripts reference `docker-compose.infra.yaml`, `docker-compose.api.yaml`,
and `docker-compose.ui.yaml`. These files already exist in the repo root.

Commit them before deploying:

```bash
git add docker-compose.infra.yaml docker-compose.api.yaml docker-compose.ui.yaml
git commit -m "feat: add docker-compose split for AWS layered deployment"
git push
```

---

## Step 4 — Deploy in order

```bash
# Use make for convenience (see Makefile), or run each manually:

cd layers/01-infra && terraform init && terraform apply
# Wait for READY file: ssh ubuntu@<infra_public_ip> 'tail -f /var/log/rag-init.log'

cd ../02-api && terraform init && terraform apply
# Wait for READY file: ssh ubuntu@<api_public_ip> 'tail -f /var/log/rag-init.log'

cd ../03-ui && terraform init && terraform apply
# Wait for READY file: ssh ubuntu@<ui_public_ip> 'tail -f /var/log/rag-init.log'

cd ../04-endpoints && terraform init && terraform apply
# Get the ALB URL: terraform output alb_dns_name
```

**Boot time per EC2:** infra ~15 min, api ~25 min (includes Ollama model pull), ui ~15 min.

---

## Step 5 — Verify

```bash
ALB_DNS=$(cd layers/04-endpoints && terraform output -raw alb_dns_name)
./check-stack.sh $ALB_DNS
```

Or manually:
- `http://<alb_dns>/` → loads the Nuke RAG UI
- `http://<alb_dns>/api/v1/health` → `{"status": "ok"}`
- `http://<infra_public_ip>:3001/` → Langfuse (admin access only)
- `http://<infra_public_ip>:3000/` → Grafana (admin/admin)

---

## Debugging a failed boot

If an EC2 doesn't reach the READY state:

```bash
# SSH in
ssh ubuntu@<ec2_public_ip> -i ~/.ssh/rag-key

# Watch the bootstrap log in real time
sudo tail -f /var/log/rag-init.log

# Check for failure sentinel
cat ~/FAILED 2>/dev/null && echo "FAILED" || echo "No failure sentinel"

# Check docker services (on infra EC2)
docker compose -f docker-compose.infra.yaml ps
```

---

## Independent redeploy

After initial setup, each layer can be redeployed independently:

```bash
# Redeploy only the API (e.g., after a code change)
cd layers/02-api && terraform apply

# The infra and ui layers are NOT touched
```

**Warning:** If you replace the infra EC2 (new private IP), immediately re-apply layers 02 and 03.

---

## Teardown (destroy order is reverse of deploy order)

```bash
cd layers/04-endpoints && terraform destroy
cd ../03-ui           && terraform destroy
cd ../02-api          && terraform destroy
cd ../01-infra        && terraform destroy
# Bootstrap is intentionally left — delete manually if needed
```
