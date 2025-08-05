# Jenkins SSH Agent with Ansible

This Docker image provides a Jenkins SSH agent with Ansible pre-installed for HomeLab CI/CD operations.

## Features

- Based on official `jenkins/ssh-agent` image
- Ansible and dependencies pre-installed
- Python modules for Ansible automation
- Optimized for ARM64 architecture
- SSH-based connection (no JNLP required)

## Building

```bash
# Build for ARM64 (registry URL configurable in group_vars/all.yml)
docker buildx build --platform linux/arm64 -t registry.example.com/homelab/jenkins-ssh-agent-ansible:latest .

# Push to registry
docker push registry.example.com/homelab/jenkins-ssh-agent-ansible:latest
```

## Usage

The agent runs as a Docker container exposing SSH on port 2222:

```bash
docker run -d \
  --name jenkins-ssh-agent \
  -e JENKINS_AGENT_SSH_PUBKEY="<jenkins_public_key>" \
  -p 2222:22 \
  -v jenkins-agent-data:/home/jenkins/agent \
  registry.example.com/homelab/jenkins-ssh-agent-ansible:latest
```

**Note**: Registry URL is configurable via `docker_registry_homelab_base_url` variable in `group_vars/all.yml`

## Environment Variables

- `JENKINS_AGENT_SSH_PUBKEY`: The public SSH key from Jenkins controller (required)

## Volumes

- `/home/jenkins/agent`: Agent workspace directory

## Ports

- `22`: SSH server (map to 2222 on host)

## Security

The agent only accepts connections authenticated with the Jenkins controller's SSH key.