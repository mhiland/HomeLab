# GitLab Runner with Ansible for HomeLab CI/CD
FROM gitlab/gitlab-runner:latest

USER root

# Install Docker CLI and Ansible dependencies
RUN apt-get update && \
    apt-get install -y \
        ca-certificates \
        curl \
        gnupg \
        lsb-release \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y \
        docker-ce-cli \
        docker-compose-plugin \
        ansible \
        sshpass \
        openssh-client \
        git \
        jq \
        python3-yaml \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create ansible user and set up SSH directory
RUN useradd -m -s /bin/bash ansible && \
    mkdir -p /home/ansible/.ssh && \
    chown -R ansible:ansible /home/ansible/.ssh && \
    chmod 700 /home/ansible/.ssh

# Set environment variables for Ansible
ENV ANSIBLE_HOST_KEY_CHECKING=False
ENV ANSIBLE_STDOUT_CALLBACK=yaml
ENV ANSIBLE_CALLBACKS_ENABLED=timer,profile_tasks

# Verify Ansible installation and add build timestamp (as root)
RUN ansible --version && \
    echo "Build timestamp: $(date)" > /opt/build-info.txt

# Switch back to gitlab-runner user
USER gitlab-runner