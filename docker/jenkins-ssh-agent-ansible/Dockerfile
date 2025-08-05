# Jenkins SSH Agent with Ansible for HomeLab CI/CD
FROM jenkins/ssh-agent:latest

USER root

# Install Ansible and dependencies
RUN apt-get update && \
    apt-get install -y \
        ansible \
        sshpass \
        openssh-client \
        git \
        curl \
        jq \
        python3-yaml \
        python3-jinja2 \
        python3-cryptography \
        rsync \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for Ansible
ENV ANSIBLE_HOST_KEY_CHECKING=False
ENV ANSIBLE_STDOUT_CALLBACK=yaml
ENV ANSIBLE_CALLBACKS_ENABLED=timer,profile_tasks

# Verify Ansible installation and add build timestamp
RUN ansible --version && \
    echo "Build timestamp: $(date)" > /opt/build-info.txt

# Set working directory
WORKDIR /home/jenkins/agent

# Use the original entrypoint from jenkins/ssh-agent
# The base image handles all SSH configuration automatically