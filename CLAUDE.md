# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a HomeLab infrastructure repository containing Ansible playbooks and roles for managing:
- SSL Certificate generation and deployment using internal CA
- HashiCorp Vault cluster deployment with raft storage
- System patching automation (nightly/monthly) - automated via Jenkins
- Synology NAS SSL certificate renewal
- Monitoring stack deployment (Prometheus exporters) for integration with hosted Grafana/Prometheus
- Docker installation and GitLab Runner deployment for CI/CD pipelines
- Jenkins agent deployment for distributed builds

**Note**: All hostnames, IP addresses, and domain names in this documentation are examples. Update your inventory files and configurations with your actual infrastructure details.

## Architecture

### Ansible Structure
- **Inventory**: `inventories/homelab/hosts` with group variables in `inventories/homelab/group_vars/all.yml`
- **Roles**: Modular roles for certificates, vault deployment, OS patching, and monitoring
- **Playbooks**: Task-specific playbooks in `playbooks/` directory

### Certificate Management
The certificate system uses a 3-stage workflow:
1. **Generate**: CSR generation on target hosts
2. **Sign**: Certificate signing with internal CA (delegated to localhost)  
3. **Distribute**: Deploy signed certificates to target systems

### Vault Cluster
- Primary/secondary raft cluster configuration
- Automatic initialization and configuration
- ARM64 binary deployment

### System Patching
- **Ansible-based patching**: Automated nightly and monthly patching using Ansible playbooks
- **Jenkins Integration**: Automated via Jenkins pipelines with environment variables
- **Unattended Operation**: Enhanced with timeout, retry logic, and dpkg configuration
- **Configuration**: Uses Jenkins environment variables for automated execution

### Monitoring Stack
- **Node Exporter**: System metrics collection (CPU, memory, disk, network) on port 9100
- **Process Exporter**: Optional application-specific monitoring on port 9256
- **Integration**: Designed for hosted Prometheus/Grafana (e.g., https://prometheus.example.com/)
- **Security**: Firewall rules and systemd hardening
- **Architecture**: ARM64 binaries for Raspberry Pi deployment, x86_64 binaries for Fedora servers
- **Multi-Architecture Support**: Separate playbooks for different architectures

### Docker and GitLab Runners
- **Docker CE**: Full Docker installation for ARM64 Raspberry Pi hosts and x86_64 Fedora servers
- **Multi-Platform Support**: Separate roles for Debian-based (Pi) and Fedora systems
- **GitLab Runners**: Instance runners deployed as Docker containers
- **Resource Management**: CPU/memory limits configured for Pi hardware
- **Security**: Runner tokens managed via environment variables
- **Architecture**: ARM64-compatible images and binaries for Pi, x86_64 for Fedora

### Jenkins Agents
- **Jenkins SSH Agents**: Distributed build agents deployed as Docker containers
- **SSH Connection**: SSH-based agents listening on port 2222
- **Docker-in-Docker**: Enabled for building containers within agents
- **Resource Management**: 1GB memory, 1 CPU limit per agent
- **Security**: SSH key authentication, public key via environment variable
- **Architecture**: ARM64-compatible Jenkins SSH agent images with Ansible pre-installed

### Jenkins Pipeline Structure
Jenkins pipelines are organized in the `jenkins/` directory by function:
- **jenkins/patching/Jenkinsfile-nightly**: Automated nightly patching (2:00 AM daily, can be triggered manually)
- **jenkins/patching/Jenkinsfile-monthly**: Automated monthly patching (first Sunday 3:00 AM, can be triggered manually)
- **jenkins/gitlab-runner/Jenkinsfile**: GitLab Runner image build and deployment (monthly maintenance)
- **jenkins/certificates/Jenkinsfile**: SSL certificate generation and deployment
- **jenkins/jenkins-agent/Jenkinsfile**: Jenkins agent deployment and management
- **Structure**: Each pipeline is in its own subdirectory with descriptive names
- **Path References**: Pipelines use relative paths (`../../ansible/`) to access Ansible resources

## Testing and Validation

### Syntax Validation
```bash
# Run comprehensive syntax validation
./ansible/test_ansible_syntax.sh

# This script validates:
# - YAML syntax for all playbooks
# - Role structure and YAML files
# - Shell script syntax validation
# - Jenkins pipeline file structure
# - Provides configuration summaries
```

## Common Commands

### Running Ansible Playbooks
```bash
# Python Management - Deploy standardized Python symlinks
ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/deploy_python_management.yml

# System patching (legacy - now handled by Jenkins)
ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/patch_systems_nightly.yml -v
ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/patch_systems_monthly.yml

# SSL Certificate workflow (run in sequence)
ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/generate_and_deploy_certs.yml --tags generate
ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/generate_and_deploy_certs.yml --tags sign  
ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/generate_and_deploy_certs.yml --tags distribute

# Vault deployment
ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/deploy_vault.yml -u <user>

# Monitoring deployment
ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/deploy_monitoring.yml

# Docker installation (supports both Raspberry Pi and Fedora)
ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/install_docker.yml

# Docker installation - Pi only
ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/install_docker.yml --limit raspberrypi

# Docker installation - Fedora only
ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/install_docker.yml --limit fedora

# GitLab Runner deployment (requires environment variables)
# Note: Use HTTPS for GitLab URL - replace with your actual GitLab instance
export GITLAB_URL="https://gitlab.example.com"
export GITLAB_RUNNER_TOKEN="glrt-xxxxxxxxxxxxx"
ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/deploy_gitlab_runner.yml

# Jenkins SSH Agent deployment (requires environment variables)
export JENKINS_AGENT_SSH_PUBKEY="ssh-rsa AAAAB3..."
ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/deploy_jenkins_ssh_agent.yml

# Register agents with Jenkins (requires environment variables)
export JENKINS_URL="https://jenkins.example.com"
export JENKINS_USER="username"
export JENKINS_TOKEN="api-token"
ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/register_jenkins_ssh_nodes.yml

# Remove agents from Jenkins
ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/register_jenkins_ssh_nodes.yml -e node_action=remove
```

### Python Management
**Documentation**: [Python Deployment Guide](docs/PYTHON_DEPLOYMENT_GUIDE.md)

```bash
# Deploy standardized Python symlinks to all hosts (fast - ~30 seconds)
ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/deploy_python_management.yml

# Test connectivity with managed Python
ansible all -i ansible/inventories/homelab/hosts -m ping

# Check Python versions across cluster
ansible raspberrypi -i ansible/inventories/homelab/hosts -m shell -a "/opt/python3.11/bin/python3 --version"

# Verify symlinks are correct
ansible raspberrypi -i ansible/inventories/homelab/hosts -m shell -a "ls -la /opt/python3.11/bin/"
```

### System Patching (Jenkins Ansible Plugin)
```bash
# Jenkins Ansible Plugin execution (recommended)
# Use "Invoke Ansible Playbook" build step in Jenkins jobs

# Daily patching playbook (includes Docker cleanup)
ansible-playbook ansible/playbooks/patch_systems_nightly.yml -i inventory

# Monthly full upgrade playbook  
ansible-playbook ansible/playbooks/patch_systems_monthly.yml -i inventory

# Manual testing with existing inventory
ansible-playbook -i inventories/homelab/hosts ansible/playbooks/patch_systems_nightly.yml

# Docker cleanup configuration
# Nightly patching automatically includes Docker cleanup for:
# - Orphaned/dangling images (docker image prune -f)
# - Stopped containers (docker container prune -f)
# - Unused networks (docker network prune -f)
# - Build cache (docker builder prune -f)
# Cleanup is safely skipped on hosts without Docker installed
```

### GitLab Runner Maintenance (Jenkins Pipeline)
```bash
# Jenkins Pipeline execution (recommended for monthly maintenance)
# Job: homelab-gitlab-runner-maintenance

# Monthly maintenance - build and deploy
# ACTION_TYPE: build-and-deploy
# SERIAL_PERCENTAGE: 25%
# DRY_RUN: false

# Security updates only - build without deploy
# ACTION_TYPE: build-only  
# FORCE_REBUILD: true

# Deploy existing image
# ACTION_TYPE: deploy-only
# SERIAL_PERCENTAGE: 50%

# Manual testing
# ACTION_TYPE: build-and-deploy
# DRY_RUN: true
# TARGET_HOSTS: pi1
```

### Vault Operations
```bash
# Check cluster status (replace vault-server with your actual Vault hostname)
vault operator raft list-peers -address=https://vault-server.example.com:8200 -format=json
vault status -address=https://vault-server.example.com:8200

# Unseal vault
vault operator unseal <unseal_key> -address=https://vault-server.example.com:8200

# View logs
journalctl -u vault -n 50 --no-pager
```

### SSL Certificate Management
```bash
# SSL Certificate renewal is now handled via Ansible playbooks
# See SSL Certificate workflow above for current process

# Manual CA operations  
openssl req -x509 -new -nodes -keyout internal-ca.key -out internal-ca.crt -days 3650 -subj "/CN=Internal CA"
openssl x509 -in internal-ca.crt -text -noout
```

### Monitoring Operations
```bash
# Deploy monitoring to all Raspberry Pi hosts
ansible-playbook -i inventories/homelab/hosts playbooks/deploy_monitoring.yml

# Deploy monitoring to Fedora hosts (x86_64 architecture)
ansible-playbook -i inventories/homelab/hosts playbooks/deploy_monitoring_fedora.yml

# Deploy with process monitoring enabled
ansible-playbook -i inventories/homelab/hosts playbooks/deploy_monitoring.yml -e "process_exporter_enabled=true"

# Check monitoring service status
ansible raspberrypi -i inventories/homelab/hosts -m systemd -a "name=node_exporter state=started"
ansible fedora -i inventories/homelab/hosts -m systemd -a "name=node_exporter state=started"

# Test local metrics endpoints (replace with your actual host IPs)
curl http://192.168.1.101:9100/metrics  # pi1
curl http://192.168.1.102:9100/metrics  # pi2
curl http://192.168.1.103:9100/metrics  # pi3
curl http://192.168.1.104:9100/metrics  # pi4
curl http://192.168.1.105:9100/metrics  # fedora-server-01

# View monitoring service logs
ansible raspberrypi -i inventories/homelab/hosts -m shell -a "journalctl -u node_exporter -n 20 --no-pager"
ansible fedora -i inventories/homelab/hosts -m shell -a "journalctl -u node_exporter -n 20 --no-pager"
```

### Docker and GitLab Runner Operations
```bash
# Update GitLab Runners with latest Ansible image 
# Note: Jenkins pipeline (homelab-gitlab-runner-maintenance) is recommended for production
export GITLAB_RUNNER_TOKEN="your-token-here"
./scripts/update-gitlab-runners.sh

# Build only (without deployment) - useful for local testing
./scripts/update-gitlab-runners.sh --build-only

# Deploy only (without rebuilding image) - useful for quick updates
./scripts/update-gitlab-runners.sh --deploy-only

# Manual build and push of Ansible image
ansible-playbook ansible/playbooks/build_gitlab_runner_image.yml

# Manual deployment of updated runners
export GITLAB_URL="https://gitlab.example.com"  # Replace with your GitLab instance URL
export GITLAB_RUNNER_TOKEN="your-token-here"    # Replace with your runner token
ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/update_gitlab_runner_monthly.yml

# Check Docker installation
ansible raspberrypi -i ansible/inventories/homelab/hosts -m shell -a "docker --version"

# View GitLab Runner status
ansible raspberrypi -i ansible/inventories/homelab/hosts -m shell -a "docker ps --filter name=gitlab-runner"

# Check runner registration
ansible raspberrypi -i ansible/inventories/homelab/hosts -m shell -a "docker exec gitlab-runner gitlab-runner list"

# View runner logs
ansible raspberrypi -i ansible/inventories/homelab/hosts -m shell -a "docker logs gitlab-runner --tail 50"

# Test Ansible availability in runner
ansible raspberrypi -i ansible/inventories/homelab/hosts -m shell -a "docker exec gitlab-runner ansible --version"
```

### Jenkins SSH Agent Operations
```bash
# Build Jenkins SSH agent image
ansible-playbook ansible/playbooks/build_jenkins_ssh_agent_image.yml

# Deploy Jenkins SSH agents
export JENKINS_AGENT_SSH_PUBKEY="ssh-rsa AAAAB3..."
ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/deploy_jenkins_ssh_agent.yml

# Deploy to specific hosts only
ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/deploy_jenkins_ssh_agent.yml --limit pi1,pi2

# Register agents with Jenkins
export JENKINS_URL="https://jenkins.example.com"  # Replace with your Jenkins URL
export JENKINS_TOKEN="your-api-token"             # Replace with your Jenkins API token
ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/register_jenkins_ssh_nodes.yml

# Register specific hosts only
ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/register_jenkins_ssh_nodes.yml --limit pi1,pi2

# Remove nodes from Jenkins
ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/register_jenkins_ssh_nodes.yml -e node_action=remove

# Check SSH agent status
ansible raspberrypi -i ansible/inventories/homelab/hosts -m shell -a "docker ps --filter name=jenkins-ssh-agent"

# Test SSH connectivity
ansible raspberrypi -i ansible/inventories/homelab/hosts -m shell -a "nc -zv localhost 2222"

# View agent logs
ansible raspberrypi -i ansible/inventories/homelab/hosts -m shell -a "docker logs jenkins-ssh-agent --tail 50"

# Restart agents
ansible raspberrypi -i ansible/inventories/homelab/hosts -m shell -a "docker restart jenkins-ssh-agent"
```

## Configuration

### Setting Up Your Infrastructure
Before using this repository, you'll need to configure it for your specific infrastructure:

1. **Update Inventory File**: Edit `ansible/inventories/homelab/hosts` with your actual hostnames and IP addresses
2. **Configure Group Variables**: Update files in `ansible/inventories/homelab/group_vars/` with your specific settings
3. **Environment Variables**: Set required environment variables for GitLab runners, Jenkins agents, etc.
4. **Certificate Configuration**: Update CA paths and certificate settings for your domain

### Key Variables (group_vars/all.yml)
- `internal_ca_key`: Path to CA private key
- `internal_ca_cert`: Path to CA certificate  
- `cert_days`: Certificate validity period (1095 days)
- `certs_dir`: Target certificate directory

### Vault Configuration (roles/vault/defaults/main.yml)
- `vault_version`: Configurable version with SHA256 checksum verification
- `vault_bind_addr`: Configurable bind address
- `vault_storage_path`: Configurable raft storage path

### System Patching Configuration
- **Jenkins Ansible Plugin** (recommended approach):
  - Install Jenkins Ansible Plugin for native integration
  - Configure SSH credentials in Jenkins credential store
  - Use dynamic inventory or existing inventory files
  - See `docs/jenkins_job_examples.md` for complete job configurations
- **Manual Execution**: Use existing Ansible inventory in `inventories/homelab/hosts`
- **Enhanced Features**: Timeouts, retries, parallel execution, comprehensive logging

### Monitoring Configuration (group_vars/monitoring.yml)
- **Node Exporter**: Version 1.7.0 on port 9100 with ARM64 binaries (Pi) and x86_64 binaries (Fedora)
- **Process Exporter**: Optional, version 0.7.10 on port 9256
- **Firewall**: Automatic firewall rule configuration (UFW for Pi, firewalld for Fedora)
- **Integration**: Configured for hosted Prometheus (e.g., https://prometheus.example.com/)
- **Prometheus Scrape Config**: Reference configuration provided for external Prometheus setup
- **Architecture Support**: 
  - `group_vars/fedora.yml`: x86_64 binary URLs and `/usr/bin/python3` interpreter
  - Default configuration in `group_vars/all.yml`: ARM64 binaries and `/opt/python3.11/bin/python3`

#### Fedora Prerequisites
- **Passwordless Sudo**: Configure with `echo 'username ALL=(ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/username`
- **SSH Host Keys**: Add to known_hosts for first-time connections
- **Python Path**: Automatically configured via `group_vars/fedora.yml`

### Docker Configuration
#### Raspberry Pi (roles/docker/defaults/main.yml)
- **Docker CE**: Latest stable version for ARM64
- **Docker Compose**: Standalone binary and plugin versions
- **Resource Limits**: Configured for Raspberry Pi constraints
- **Storage Driver**: overlay2 for optimal performance

#### Fedora (roles/docker_fedora/defaults/main.yml)
- **Docker CE**: Latest stable version for x86_64
- **Package Manager**: Uses DNF instead of APT
- **Repository**: Official Docker Fedora repository
- **Docker Compose**: x86_64 standalone binary via group_vars/fedora.yml

### GitLab Runner Configuration (roles/gitlab_runner_docker/defaults/main.yml)
- **Executor**: Docker executor with privileged mode
- **Resource Limits**: 1GB memory, 1 CPU per runner
- **Environment Variables**: 
  - `GITLAB_URL`: Your GitLab instance URL (e.g., https://gitlab.example.com)
  - `GITLAB_RUNNER_TOKEN`: Runner authentication token (glrt- prefix)
- **Tags**: raspberrypi, arm64, docker, instance
- **Concurrent Jobs**: Limited to 1 per Pi for resource management

### Jenkins SSH Agent Configuration (roles/jenkins_agent_ssh/defaults/main.yml)
- **Connection**: SSH-based connection on port 2222
- **Resource Limits**: 1GB memory, 1 CPU per agent
- **Environment Variables**:
  - `JENKINS_AGENT_SSH_PUBKEY`: SSH public key from Jenkins controller
- **Features**: Docker-in-Docker enabled, Ansible pre-installed
- **Restart Policy**: Unless-stopped with SSH health checks
- **Jenkins Credentials**: SSH private key stored as Jenkins credential (ID: jenkins-ssh-key)
- **Deployment**: 10-minute timeout for image pull, 15-minute total timeout per host

### Docker Cleanup Configuration (roles/docker_cleanup/defaults/main.yml)
- **Automatic Cleanup**: Integrated into nightly patching (enabled by default)
- **Safe Operations**: Only removes orphaned/dangling resources, never tagged images
- **Cleanup Targets**:
  - **Images**: Dangling/orphaned images (`docker image prune -f`)
  - **Containers**: Stopped containers (`docker container prune -f`)
  - **Networks**: Unused networks (`docker network prune -f`)
  - **Build Cache**: Docker build cache (`docker builder prune -f`)
  - **Volumes**: Disabled by default for safety (`docker_cleanup_volumes: false`)
- **Smart Detection**: Automatically skips cleanup on hosts without Docker
- **Logging**: Reports disk space reclaimed and cleanup status in Jenkins artifacts

## Target Infrastructure
- ARM64 architecture hosts (Raspberry Pi) and x86_64 hosts (Fedora servers)
- Multi-platform support with platform-specific roles and configurations
- Configurable host groups for different services
- Vault UI and health check endpoints configurable
- Monitoring endpoints (9100, 9256) for external Prometheus integration

**Example Infrastructure Layout**:
```
pi1 (192.168.1.101)     - Raspberry Pi 4, ARM64
pi2 (192.168.1.102)     - Raspberry Pi 4, ARM64  
pi3 (192.168.1.103)     - Raspberry Pi 4, ARM64
pi4 (192.168.1.104)     - Raspberry Pi 4, ARM64
fedora-server-01 (192.168.1.105) - x86_64 server
```

## Commit Message Guidelines
- Use concise, descriptive commit messages
- DO NOT include "Generated with Claude Code" or "Co-Authored-By" lines