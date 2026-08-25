# Remote deploy targets — run from a workstation, executed on the server.
# Requires an ssh alias (or host) with sudo rights on the VPS; override
# the default with e.g. `make deploy DEPLOY_HOST=myalias`.

DEPLOY_HOST ?= bibliotekarien-vps
DEPLOY_SCRIPT = /opt/markrounding/app/scripts/deploy.sh

.PHONY: deploy deploy-check deploy-logs

# ssh -t: sudo must be able to prompt for a password.
deploy:
	ssh -t $(DEPLOY_HOST) 'sudo $(DEPLOY_SCRIPT)'

deploy-check:
	ssh -t $(DEPLOY_HOST) 'sudo $(DEPLOY_SCRIPT) --check'

deploy-logs:
	ssh -t $(DEPLOY_HOST) "sudo bash -c 'cd /opt/markrounding/app && docker compose -f docker-compose.prod.yml logs --tail=50 web'"
