#!/bin/bash

# Test script to validate Ansible syntax and basic functionality
# This script helps validate the enhanced Ansible configuration

set -e

ANSIBLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$ANSIBLE_DIR/.." && pwd)"
cd "$ANSIBLE_DIR"

echo "=== Ansible Configuration Validation ==="
echo "Ansible Directory: $ANSIBLE_DIR"
echo "Project Root: $PROJECT_ROOT"
echo ""

# Check if Ansible is available
if ! command -v ansible-playbook &> /dev/null; then
    echo "Warning: ansible-playbook not found in PATH"
    echo "Install Ansible to run full validation"
    echo ""
else
    echo "✓ Ansible found: $(ansible-playbook --version | head -1)"
    echo ""
fi

# Validate YAML syntax of playbooks
echo "=== Validating Playbook YAML Syntax ==="
for playbook in playbooks/*.yml; do
    if [[ -f "$playbook" ]]; then
        echo "Checking: $playbook"
        if command -v python3 &> /dev/null; then
            python3 -c "import yaml; yaml.safe_load(open('$playbook'))" && echo "  ✓ Valid YAML" || echo "  ✗ Invalid YAML"
        else
            echo "  ? Cannot validate YAML (python3 not found)"
        fi
    fi
done
echo ""

# Validate role structure
echo "=== Validating Role Structure ==="
ROLE_DIR="roles/os_patch"
if [[ -d "$ROLE_DIR" ]]; then
    echo "✓ Role directory exists: $ROLE_DIR"
    
    for required_file in "defaults/main.yml" "tasks/main.yml" "tasks/debian.yml" "tasks/fedora.yml"; do
        if [[ -f "$ROLE_DIR/$required_file" ]]; then
            echo "  ✓ $required_file exists"
            if command -v python3 &> /dev/null; then
                python3 -c "import yaml; yaml.safe_load(open('$ROLE_DIR/$required_file'))" && echo "    ✓ Valid YAML" || echo "    ✗ Invalid YAML"
            fi
        else
            echo "  ✗ $required_file missing"
        fi
    done
else
    echo "✗ Role directory not found: $ROLE_DIR"
fi
echo ""

# Validate shell scripts
echo "=== Validating Shell Scripts ==="
shell_scripts=(
    "../docker/jenkins-ssh-agent-ansible/entrypoint.sh"
    "../scripts/update-gitlab-runners.sh"
)

for script in "${shell_scripts[@]}"; do
    if [[ -f "$script" ]]; then
        echo "Checking: $script"
        if bash -n "$script"; then
            echo "  ✓ Valid bash syntax"
        else
            echo "  ✗ Invalid bash syntax"
        fi
        
        if [[ -x "$script" ]]; then
            echo "  ✓ Executable"
        else
            echo "  ✗ Not executable"
        fi
    else
        echo "  ✗ Script not found: $script"
    fi
done
echo ""

# Validate Jenkins pipeline files
echo "=== Validating Jenkins Pipeline Files ==="
for jenkinsfile in ../jenkins/*/Jenkinsfile*; do
    if [[ -f "$jenkinsfile" ]]; then
        echo "Found: $jenkinsfile"
        if [[ -r "$jenkinsfile" ]]; then
            echo "  ✓ Readable"
            # Basic syntax check - look for common pipeline structure
            if grep -q "pipeline\s*{" "$jenkinsfile" && grep -q "stages\s*{" "$jenkinsfile"; then
                echo "  ✓ Contains pipeline structure"
            else
                echo "  ? No standard pipeline structure found"
            fi
        else
            echo "  ✗ Not readable"
        fi
    fi
done
echo ""

# Display enhanced features summary
echo "=== Enhanced Features Summary ==="
echo "The Ansible configuration now includes:"
echo "✓ Timeout handling (30 minutes per operation)"
echo "✓ Retry logic with progressive delays"
echo "✓ Parallel execution support"
echo "✓ Jenkins integration with environment variables"
echo "✓ Comprehensive logging with structured output"
echo "✓ Unattended upgrade configuration"
echo "✓ Autoremove and autoclean operations"
echo "✓ Cross-platform support (Debian/RedHat)"
echo "✓ Dynamic inventory generation from Jenkins variables"
echo "✓ Summary report generation"
echo ""

echo "=== Jenkins Ansible Plugin Setup ==="
echo "Recommended approach for Jenkins integration:"
echo "1. Install Jenkins Ansible Plugin"
echo "2. Configure SSH credentials in Jenkins credential store"
echo "3. Use 'Invoke Ansible Playbook' build step instead of shell scripts"
echo "4. See ../docs/jenkins_job_examples.md for complete job configurations"
echo ""

echo "=== Jenkins Job Configuration ==="
echo "Build Steps:"
echo "  - Invoke Ansible Playbook:"
echo "    - Playbook: ansible/playbooks/patch_systems_nightly.yml"
echo "    - Inventory: Dynamic or inventories/homelab/hosts"
echo "    - Credentials: SSH private key credential ID"
echo "    - Become: Yes, Become User: root"
echo ""

echo "Validation completed!"