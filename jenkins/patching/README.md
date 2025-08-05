# HomeLab Patching Jenkins Pipelines

This directory contains Jenkins pipeline configurations for automated system patching.

## Pipeline Files

### Jenkinsfile-nightly (Automated Nightly)
- **Purpose**: Automated safe patching every night
- **Schedule**: Daily at 2:00 AM (`0 2 * * *`)
- **Updates**: Security updates only (safe upgrades)
- **Timeout**: 30 minutes
- **Target**: All hosts by default

### Jenkinsfile-monthly (Automated Monthly)
- **Purpose**: Automated full system upgrades monthly
- **Schedule**: First Sunday of each month at 3:00 AM (`0 3 1-7 * 0`)
- **Updates**: Full package upgrades (may include kernel updates)
- **Timeout**: 90 minutes
- **Target**: All hosts by default
- **Features**: Extended verification, reboot requirement checking

## Jenkins Job Setup

Create two separate Jenkins jobs:

### 1. homelab-patching-nightly
```groovy
// Pipeline script from SCM
// Repository: your-homelab-repo
// Script Path: jenkins/patching/Jenkinsfile-nightly
// Build triggers: Configured in Jenkinsfile (cron: 0 2 * * *)
```

### 2. homelab-patching-monthly
```groovy
// Pipeline script from SCM
// Repository: your-homelab-repo
// Script Path: jenkins/patching/Jenkinsfile-monthly
// Build triggers: Configured in Jenkinsfile (cron: 0 3 1-7 * 0)
```

## Required Jenkins Configuration

### Credentials
- `ansible-inventory-homelab`: Secret file containing Ansible inventory
- `ansible-ssh-key`: SSH private key for connecting to hosts

### Agents
- Agent with label `ansible` that has Ansible installed
- Python 3 and required Ansible modules

### Environment Variables
All required environment variables are set within the Jenkinsfiles.

## Schedule Details

| Job | Schedule | Frequency | Type | Risk Level |
|-----|----------|-----------|------|------------|
| Nightly | 2:00 AM daily | Every day | Security only | Low |
| Monthly | 3:00 AM first Sunday | Monthly | Full upgrade | Medium |

## Monitoring

### Nightly Patching
- Should complete in 15-30 minutes
- Low risk of requiring reboots
- Safe to run unattended

### Monthly Patching
- May take 60-90 minutes
- Higher likelihood of kernel updates
- May require reboots (check job output)
- Monitor systems for 24-48 hours after

## Troubleshooting

### Common Issues
1. **SSH connectivity failures**: Check agent SSH keys and host availability
2. **Inventory file missing**: Verify `ansible-inventory-homelab` credential
3. **Timeout errors**: Increase timeout values in monthly pipeline for slow networks
4. **Python interpreter errors**: Ensure managed Python is deployed (see Python Deployment Guide)

### Manual Intervention
Both pipelines can be triggered manually for:
- Testing changes before automated runs
- Patching specific hosts only (use TARGET_HOSTS parameter)
- Running dry-run mode to preview changes (set DRY_RUN=true)
- Emergency patching outside normal schedule

## Logs and Artifacts

Each pipeline archives:
- Ansible execution logs
- System status reports
- Patching summary files
- Reboot requirement reports (monthly)

## Integration with Python Management

All pipelines include `ANSIBLE_ROLES_PATH=roles` to work with the Python management system that provides standardized Python interpreters across the cluster.