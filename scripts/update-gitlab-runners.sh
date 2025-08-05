#!/bin/bash

# Update GitLab Runners with latest Ansible image
# This script builds a new image and deploys it to all Raspberry Pi hosts

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Default environment variables
GITLAB_URL="${GITLAB_URL:-https://gitlab.example.com}"
GITLAB_RUNNER_TOKEN="${GITLAB_RUNNER_TOKEN:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Update GitLab Runners with latest Ansible-enabled image"
    echo ""
    echo "Options:"
    echo "  --build-only     Only build and push the image (don't deploy)"
    echo "  --deploy-only    Only deploy to runners (don't build)"
    echo "  --help           Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  GITLAB_URL       GitLab instance URL (default: https://gitlab.example.com)"
    echo "  GITLAB_RUNNER_TOKEN  GitLab runner registration token (required)"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Build and deploy"
    echo "  $0 --build-only                      # Only build image"
    echo "  GITLAB_RUNNER_TOKEN=xxx $0           # With token"
}

check_requirements() {
    echo -e "${YELLOW}Checking requirements...${NC}"
    
    # Check if we're in the right directory
    if [[ ! -f "$PROJECT_ROOT/ansible/playbooks/update_gitlab_runner_monthly.yml" ]]; then
        echo -e "${RED}Error: Must be run from HomeLab project directory${NC}"
        exit 1
    fi
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker is required but not installed${NC}"
        exit 1
    fi
    
    # Check Ansible
    if ! command -v ansible-playbook &> /dev/null; then
        echo -e "${RED}Error: Ansible is required but not installed${NC}"
        exit 1
    fi
    
    # Check GitLab token for deployment
    if [[ "$BUILD_ONLY" != "true" && -z "$GITLAB_RUNNER_TOKEN" ]]; then
        echo -e "${RED}Error: GITLAB_RUNNER_TOKEN environment variable is required${NC}"
        echo "Get your token from: $GITLAB_URL/-/admin/runners"
        exit 1
    fi
    
    echo -e "${GREEN}Requirements check passed${NC}"
}

build_image() {
    echo -e "${YELLOW}Building GitLab Runner image with Ansible...${NC}"
    
    cd "$PROJECT_ROOT"
    ansible-playbook ansible/playbooks/build_gitlab_runner_image.yml
    
    echo -e "${GREEN}Image build completed${NC}"
}

deploy_runners() {
    echo -e "${YELLOW}Deploying updated runners to Raspberry Pi cluster...${NC}"
    
    cd "$PROJECT_ROOT"
    
    export GITLAB_URL
    export GITLAB_RUNNER_TOKEN
    export ANSIBLE_ROLES_PATH=ansible/roles
    
    ansible-playbook \
        -i ansible/inventories/homelab/hosts \
        ansible/playbooks/update_gitlab_runner_monthly.yml
    
    echo -e "${GREEN}Deployment completed${NC}"
}

# Parse command line arguments
BUILD_ONLY=false
DEPLOY_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --build-only)
            BUILD_ONLY=true
            shift
            ;;
        --deploy-only)
            DEPLOY_ONLY=true
            shift
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            exit 1
            ;;
    esac
done

# Validate conflicting options
if [[ "$BUILD_ONLY" == "true" && "$DEPLOY_ONLY" == "true" ]]; then
    echo -e "${RED}Error: --build-only and --deploy-only cannot be used together${NC}"
    exit 1
fi

# Main execution
echo -e "${GREEN}GitLab Runner Update Script${NC}"
echo "Project: $PROJECT_ROOT"
echo "GitLab URL: $GITLAB_URL"
echo ""

check_requirements

if [[ "$DEPLOY_ONLY" == "true" ]]; then
    deploy_runners
elif [[ "$BUILD_ONLY" == "true" ]]; then
    build_image
else
    build_image
    echo ""
    deploy_runners
fi

echo ""
echo -e "${GREEN}✅ GitLab Runner update completed successfully!${NC}"
echo ""
echo "Your runners are now updated with the latest Ansible-enabled image."
echo "Check status at: $GITLAB_URL/-/admin/runners"