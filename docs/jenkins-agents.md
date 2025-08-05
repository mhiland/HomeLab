# Jenkins SSH Agents - Deployment and Troubleshooting Guide

> **Note**: All hostnames in this document (pi1, pi2, etc.) are generic examples. Replace them with your actual infrastructure hostnames when using these commands.

This document provides a comprehensive guide for deploying Jenkins SSH agents using Ansible automation and troubleshooting common issues.

## Overview

Jenkins SSH agents are deployed as Docker containers on Raspberry Pi hosts using Ansible automation. The agents provide distributed build capabilities with Ansible pre-installed for infrastructure automation tasks.

## Automated Deployment

### Quick Start

```bash
# 1. Deploy SSH agents to Pi hosts
export JENKINS_AGENT_SSH_PUBKEY="ssh-ed25519 AAAAC3... your-public-key"
ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/deploy_jenkins_ssh_agent.yml

# 2. Register agents with Jenkins
export JENKINS_URL="https://jenkins.example.com"
export JENKINS_USER="username" 
export JENKINS_TOKEN="api-token"
ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/register_jenkins_ssh_nodes.yml
```

### Architecture

```
Jenkins Master → SSH (port 2222) → Pi Host → Docker Container (SSH agent with Ansible)
```

The Jenkins master connects via SSH to port 2222 on the Pi host, which forwards to port 22 inside the Docker container running the SSH agent.

## Ansible Automation

The deployment is fully automated using two Ansible playbooks:

### 1. `deploy_jenkins_ssh_agent.yml`
- Pulls pre-built Docker image from private registry
- Creates required directories with proper ownership
- Deploys Docker Compose configuration
- Handles SSH host key generation and permissions automatically
- Includes 10-minute timeout for large image pulls on ARM64

### 2. `register_jenkins_ssh_nodes.yml` 
- Registers agents with Jenkins via REST API
- Uses curl to bypass CSRF token issues
- Validates all required environment variables
- Waits for agents to come online
- Supports both creation and removal of nodes

## Key Requirements (Automated)

### 1. Docker Image and Registry
- **Image**: Configurable via `docker_registry_homelab_base_url` and `jenkins_ssh_agent_image_name` variables
- **Default**: `registry.example.com/homelab/jenkins-ssh-agent-ansible:latest`
- **Registry**: Unauthenticated private registry (configurable in group_vars/all.yml)
- **Base**: Jenkins SSH agent with Ansible and ARM64 support
- **Size**: ~975MB (requires 10-minute pull timeout)

### 2. SSH Configuration (Auto-Generated)
The Ansible role automatically creates these files in `/opt/jenkins-ssh-agent/ssh/`:

- SSH host keys (RSA, ECDSA, Ed25519) with proper permissions
- `sshd_config` with Jenkins-compatible settings
- `moduli` file to prevent SSH warnings
- Proper ownership (UID 1000) for Docker compatibility

### 3. Jenkins Configuration

- **SSH Credentials**: Must exist in Jenkins with ID `jenkins_ssh_key`
- **Private Key**: Must match the public key in `JENKINS_AGENT_SSH_PUBKEY`
- **Node Configuration**: Automatically created by registration playbook
  - Host: Pi hostname (e.g., `pi1`, `pi2`) 
  - Port: 2222 (mapped to container port 22)
  - Credentials: `jenkins_ssh_key`
  - Remote root directory: `/home/jenkins/agent`
  - Labels: `ansible`

## Common Issues and Solutions

### 1. Ansible Playbook Failures

#### "Found variable using reserved name 'action'"
**Cause**: Ansible reserves `action` as a built-in variable name.  
**Solution**: Fixed in playbook - uses `registration_action` instead.

#### "The module interpreter '/usr/bin/python3.11' was not found"
**Cause**: Ansible defaults to wrong Python path on Raspberry Pi.  
**Solution**: Fixed in playbook - sets `ansible_python_interpreter: /usr/bin/python3`.

#### "Authentication failed" / "401 Unauthorized"
**Cause**: Missing or incorrect Jenkins credentials.  
**Solution**: Ensure all environment variables are set:
```bash
export JENKINS_URL="https://jenkins.example.com"
export JENKINS_USER="username"
export JENKINS_TOKEN="api-token"
```

### 2. Docker Image Pull Issues

#### "Timeout pulling image"
**Cause**: Large image (~975MB) on slow ARM64 connection.  
**Solution**: Fixed in playbook - uses 10-minute timeout with retries.

#### "Permission denied" accessing registry
**Cause**: Registry authentication issues.  
**Solution**: Registry is unauthenticated - no login required.

### 3. SSH Connection Issues

#### Jenkins Node Shows Offline
**Debugging Steps**:
1. Check container status: `docker ps --filter name=jenkins-ssh-agent`
2. Check SSH port: `ss -tlpn | grep :2222`
3. View container logs: `docker logs jenkins-ssh-agent`
4. Test SSH connectivity: Manual SSH test (will fail without proper key)
5. Verify Jenkins credentials exist with ID `jenkins_ssh_key`

#### "Connection refused" on port 2222
**Cause**: Container not running or SSH service failed to start.
**Solution**: Check container logs and restart if needed:
```bash
docker logs jenkins-ssh-agent
docker restart jenkins-ssh-agent
```

## Deployment File Structure (Auto-Created)

```
/opt/jenkins-ssh-agent/
├── compose/
│   └── docker-compose.yml        # Docker Compose configuration
└── workspace/                    # Jenkins agent workspace (UID 1000)
```

**Note**: SSH configuration is handled automatically by the Docker image and Ansible role.

## Testing Checklist

### Automated Deployment:
- [ ] `deploy_jenkins_ssh_agent.yml` completes without errors
- [ ] Docker image pulls successfully (may take up to 10 minutes)
- [ ] Container shows as "Running" and "healthy"
- [ ] SSH port 2222 is listening: `ss -tlpn | grep :2222`

### Registration:
- [ ] All environment variables set (JENKINS_URL, JENKINS_USER, JENKINS_TOKEN, JENKINS_AGENT_SSH_PUBKEY)
- [ ] `register_jenkins_ssh_nodes.yml` completes without errors
- [ ] Jenkins node appears in web UI
- [ ] Node status shows "Online" in Jenkins

### Validation:
- [ ] SSH credentials exist in Jenkins with ID `jenkins_ssh_key`
- [ ] Test job can run successfully on agent with `ansible` label

## Environment Variables Required

### For Deployment:
```bash
export JENKINS_AGENT_SSH_PUBKEY="ssh-ed25519 AAAAC3... your-public-key"
```

### For Registration:
```bash
export JENKINS_URL="https://jenkins.example.com"
export JENKINS_USER="username" 
export JENKINS_TOKEN="api-token"
```

## Recovery Commands

When agents need to be redeployed:

```bash
# 1. Remove existing container and data (replace 'pi1' with your target host)
ansible pi1 -i ansible/inventories/homelab/hosts -m shell -a "docker stop jenkins-ssh-agent && docker rm jenkins-ssh-agent" -e ansible_python_interpreter=/usr/bin/python3
ansible pi1 -i ansible/inventories/homelab/hosts -m file -a "path=/opt/jenkins-ssh-agent state=absent" -b -e ansible_python_interpreter=/usr/bin/python3

# 2. Redeploy agent (replace 'pi1' with your target host)
export JENKINS_AGENT_SSH_PUBKEY="ssh-ed25519 AAAAC3... your-public-key"
ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/deploy_jenkins_ssh_agent.yml --limit pi1

# 3. Re-register with Jenkins (if needed, replace 'pi1' with your target host)
export JENKINS_URL="https://jenkins.example.com"
export JENKINS_USER="username"
export JENKINS_TOKEN="api-token"
ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/register_jenkins_ssh_nodes.yml --limit pi1
```

---

**Note**: This automated approach eliminates the complexity of manual SSH key management and Docker permission issues. All configuration is handled by Ansible playbooks and the pre-built Docker image.