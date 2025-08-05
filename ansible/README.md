
# HomeLab Ansible Playbooks

This repository contains Ansible playbooks and roles for managing HomeLab infrastructure on Raspberry Pi cluster.

## Available Functionality
- **System Patching**: Automated nightly and monthly patching
- **SSL Certificates**: Internal CA-based certificate generation and deployment
- **Docker Installation**: Docker CE deployment for ARM64 Raspberry Pi
- **GitLab Runners**: Docker-based GitLab CI/CD runners
- **HashiCorp Vault**: Raft-based Vault cluster deployment
- **Monitoring Stack**: Prometheus exporters (Node Exporter, Process Exporter)

## Prerequisites
- Ansible 2.9+
- Raspberry Pi cluster running Debian/Raspbian (ARM64)
- SSH access to all nodes
- For GitLab runners: GitLab instance with runner authentication token

> **Note**: All examples below use generic hostnames and URLs. Replace with your actual infrastructure details.

# Patching
## How To Run
> ansible-playbook playbooks/patch_systems_nightly.yml -v

> ansible-playbook playbooks/patch_systems_monthly.yml


# SSL Certificates

## Generate Root CA 

1. Create the Internal CA
> openssl req -x509 -new -nodes -keyout internal-ca.key -out internal-ca.crt -days 3650 -subj "/CN=Internal CA"

2. Verify Certificates
> openssl x509 -in internal-ca.crt -text -noout        # Check CA cert

Final certificate files:
- internal-ca.crt	
- internal-ca.key
- internal-ca.srl

## Store Root CA in Jenkins
1. Go to Manage Jenkins → Manage Credentials.
2. Select your credentials domain (e.g., "Global").
3. Click Add Credentials:
    - Kind: "Secret file"
    - Scope: "Global"
    - File: Upload internal-ca.key → ID: internal_ca_key
    - File: Upload internal-ca.crt → ID: internal_ca_cert
    - File: Upload internal-ca.srl → ID: internal_ca_srl
4. Save.


## Workflow
> ansible-playbook -i inventories/homelab/hosts playbooks/generate_and_deploy_certs.yml --tags generate

> ansible-playbook -i inventories/homelab/hosts playbooks/generate_and_deploy_certs.yml --tags sign

> ansible-playbook -i inventories/homelab/hosts playbooks/generate_and_deploy_certs.yml --tags distribute


## Update CA Certificates on Vault Secondary Node
> sudo cp internal-ca.crt  /usr/local/share/ca-certificates/custom.crt

> sudo update-ca-certificates

# Docker Installation

## Deploy Docker CE to Raspberry Pi Cluster
> ansible-playbook -i inventories/homelab/hosts playbooks/install_docker.yml

This installs Docker CE with ARM64 support on all Raspberry Pi hosts in the cluster.

# GitLab Runners

## Deploy GitLab Runners with Docker
Set environment variables first:
> export GITLAB_URL="https://gitlab.example.com"
> export GITLAB_RUNNER_TOKEN="glrt-xxxxxxxxxxxxx"

Deploy runners:
> ansible-playbook -i inventories/homelab/hosts playbooks/deploy_gitlab_runner.yml

## Verify Runner Status
> ansible raspberrypi -i inventories/homelab/hosts -m shell -a "docker exec gitlab-runner gitlab-runner list"

## View Runner Logs
> ansible raspberrypi -i inventories/homelab/hosts -m shell -a "docker logs gitlab-runner --tail 20"

# Vault
> ansible-playbook playbooks/deploy_vault.yml -u <user>


## Common URLs
https://vault-server.local:8200/v1/sys/health

https://vault-server.local:8200/ui/

## Common Commands

> vault operator raft list-peers -address=https://vault-server.local:8200 -format=json

> journalctl -u vault -n 50 --no-pager

> vault status -address=https://vault-server.local:8200

> vault operator unseal <unseal_key> -address=https://vault-server.local:8200
