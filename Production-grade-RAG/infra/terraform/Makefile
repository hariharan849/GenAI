SHELL := /bin/bash
LAYERS := layers/01-infra layers/02-api layers/03-ui layers/04-endpoints

.PHONY: validate-all init-all deploy-all destroy-all outputs

validate-all:
	@for layer in $(LAYERS); do \
		echo "=== Validating $$layer ==="; \
		(cd $$layer && terraform init -backend=false -input=false > /dev/null && terraform validate) || exit 1; \
	done
	@echo "All layers valid."

init-all:
	@for layer in $(LAYERS); do \
		echo "=== Initialising $$layer ==="; \
		(cd $$layer && terraform init -input=false) || exit 1; \
	done

deploy-all: init-all
	@for layer in $(LAYERS); do \
		echo "=== Applying $$layer ==="; \
		(cd $$layer && terraform apply -auto-approve) || exit 1; \
		echo ""; \
	done
	@echo "All layers deployed."
	@$(MAKE) outputs

destroy-all:
	@echo "This will destroy ALL layers in reverse order. Ctrl-C to cancel."; \
	sleep 5; \
	for layer in layers/04-endpoints layers/03-ui layers/02-api layers/01-infra; do \
		echo "=== Destroying $$layer ==="; \
		(cd $$layer && terraform destroy -auto-approve) || exit 1; \
	done
	@echo "All layers destroyed."

outputs:
	@echo "=== Layer outputs ==="
	@echo "--- 01-infra ---"
	@(cd layers/01-infra && terraform output 2>/dev/null) || true
	@echo "--- 02-api ---"
	@(cd layers/02-api && terraform output 2>/dev/null) || true
	@echo "--- 03-ui ---"
	@(cd layers/03-ui && terraform output 2>/dev/null) || true
	@echo "--- 04-endpoints ---"
	@(cd layers/04-endpoints && terraform output 2>/dev/null) || true
