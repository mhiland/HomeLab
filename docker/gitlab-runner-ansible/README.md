# GitLab Runner with Ansible

Custom Docker image based on `gitlab/gitlab-runner:latest` with Ansible pre-installed for HomeLab CI/CD pipelines.

## Features

- GitLab Runner (latest)
- Ansible with Python 3
- SSH client and sshpass for remote connections
- Common utilities (git, curl, jq)
- Optimized for ARM64 Raspberry Pi deployment

## Building

```bash
docker build -t homelab/gitlab-runner-ansible:latest .
```

## Usage

This image is used by the GitLab Runner deployment playbook. Update the `gitlab_runner_docker_image` variable to use this custom image instead of the default `docker:latest`.

## Environment Variables

- `ANSIBLE_HOST_KEY_CHECKING=False` - Disable SSH host key checking
- `ANSIBLE_STDOUT_CALLBACK=yaml` - Use YAML output format
- `ANSIBLE_CALLBACKS_ENABLED=timer,profile_tasks` - Enable timing and profiling