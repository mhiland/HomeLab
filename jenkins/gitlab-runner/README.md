# GitLab Runner Maintenance Jenkins Pipeline

This Jenkins pipeline automates the building and deployment of GitLab Runner Docker images with Ansible support for your HomeLab infrastructure.

## Pipeline Overview

The pipeline provides flexible maintenance options for your GitLab Runners:

- **Build and Deploy**: Complete workflow - builds new image and deploys to all runners
- **Build Only**: Just builds and pushes the Docker image to registry
- **Deploy Only**: Deploys existing image to runners without rebuilding

## Jenkins Job Configuration

### 1. Create New Pipeline Job

1. Go to Jenkins → New Item
2. Enter name: `homelab-gitlab-runner-maintenance`
3. Select "Pipeline" 
4. Click OK

### 2. Configure Job Parameters

The pipeline uses these parameters (auto-configured from Jenkinsfile):

- **ACTION_TYPE**: `build-and-deploy` | `build-only` | `deploy-only`
- **SERIAL_PERCENTAGE**: `25%` | `50%` | `75%` | `100%` (recommended: 25-50%)
- **DRY_RUN**: `false` | `true` (preview changes without applying)
- **TARGET_HOSTS**: `raspberrypi` (or specific hosts like `pi1,pi2`)
- **SKIP_CONNECTIVITY_CHECK**: `false` | `true`
- **FORCE_REBUILD**: `false` | `true` (force rebuild even if no changes)

### 3. Required Jenkins Credentials

Set up these credentials in Jenkins (Manage Jenkins → Credentials):

#### `ansible-inventory-homelab` (Secret File)
Upload your Ansible inventory file containing:
```ini
[raspberrypi]
pi1 ansible_host=192.168.1.101
pi2 ansible_host=192.168.1.102  
pi3 ansible_host=192.168.1.103
```

#### `gitlab-runner-token` (Secret Text)
Your GitLab Runner registration token:
```
glrt-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Get this from: GitLab → Admin Area → CI/CD → Runners → Register an instance runner

### 4. Pipeline Configuration

In the job configuration:

**Pipeline Definition**: Pipeline script from SCM
**SCM**: Git
**Repository URL**: Your HomeLab repository URL
**Script Path**: `jenkins/gitlab-runner/Jenkinsfile`

### 5. Node Requirements

Ensure your Jenkins agent has:
- Docker access (`docker` command available)
- SSH access to Pi hosts
- Network access to Docker registry (configurable in `group_vars/all.yml`, defaults to `registry.example.com`)

## Usage Examples

### Monthly Maintenance (Recommended)
- **ACTION_TYPE**: `build-and-deploy`
- **SERIAL_PERCENTAGE**: `25%`
- **DRY_RUN**: `false`
- **TARGET_HOSTS**: `raspberrypi`

This rebuilds the image with latest packages and deploys to all runners.

### Security Updates Only
- **ACTION_TYPE**: `build-only`
- **FORCE_REBUILD**: `true`

Builds fresh image with latest security updates, doesn't deploy.

### Deploy Existing Image
- **ACTION_TYPE**: `deploy-only`
- **SERIAL_PERCENTAGE**: `50%`

Deploys previously built image to runners without rebuilding.

### Test Changes
- **ACTION_TYPE**: `build-and-deploy`
- **DRY_RUN**: `true`
- **TARGET_HOSTS**: `pi1`

Preview what would happen on a single host.

## Pipeline Stages

1. **Preparation**: Setup environment and validate credentials
2. **Validate Environment**: Check required files and configurations
3. **Connectivity Check**: Verify SSH access to target hosts (optional)
4. **Pre-Update Info**: Gather current runner status
5. **Build Docker Image**: Build and push updated image (conditional)
6. **Deploy Updated Runners**: Rolling deployment to Pi hosts (conditional)
7. **Post-Update Verification**: Verify runner health and registration
8. **Generate Summary**: Create detailed execution report

## Scheduling

### Manual Execution
Run as needed when:
- Dockerfile changes
- Security updates required
- GitLab Runner issues

### Automated Monthly Schedule
Add to job configuration → Build Triggers → Build periodically:
```
# Monthly on first Sunday at 2 AM
0 2 * * 0#1
```

Or use Jenkins' cron expression for first Sunday of each month.

## Monitoring and Troubleshooting

### Verify Success
1. Check Jenkins build logs
2. Visit GitLab: Admin Area → CI/CD → Runners
3. Verify runners show as "online" with updated image

### Common Issues

**Build Fails**: Check Docker access and registry connectivity
**Deploy Fails**: Verify SSH access and Ansible inventory
**Runners Offline**: Check GitLab token validity and network connectivity

### Manual Verification
```bash
# Check runner containers
ansible raspberrypi -i inventories/homelab/hosts -m shell -a "docker ps --filter name=gitlab-runner"

# Verify Ansible availability
ansible raspberrypi -i inventories/homelab/hosts -m shell -a "docker exec gitlab-runner ansible --version"

# Test runner connectivity
ansible raspberrypi -i inventories/homelab/hosts -m shell -a "docker exec gitlab-runner gitlab-runner verify"
```

## Integration with Existing Workflows

This pipeline complements your existing Jenkins automation:

- **Patching Pipeline**: Run after monthly system patches
- **Certificate Renewal**: Can be combined with SSL cert updates
- **Monitoring Updates**: Coordinate with monitoring stack updates

## Security Considerations

- GitLab token stored as Jenkins secret
- SSH keys managed by Jenkins agent
- Registry is unauthenticated (internal network only)
- Runners updated with serial execution to minimize service disruption

## Artifacts

Each run produces:
- Detailed execution summary (Markdown)
- Ansible execution logs
- Runner status reports
- Image build logs

All artifacts are archived in Jenkins for troubleshooting and audit purposes.