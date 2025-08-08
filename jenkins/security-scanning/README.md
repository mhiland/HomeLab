# HomeLab Security Scanning Pipeline

## Overview

This comprehensive security scanning solution provides automated security monitoring for your HomeLab infrastructure using Ansible-deployed security tools and Jenkins orchestration.

## Features

### 🛡️ Security Tools Integration
- **RKhunter**: Rootkit detection and system scanning
- **Chkrootkit**: Alternative rootkit scanner for comprehensive coverage
- **AIDE**: Advanced intrusion detection and file integrity monitoring
- **Debsums**: Package integrity verification (Debian/Ubuntu)
- **Fail2ban**: Intrusion prevention system

### 🔄 Automated Scanning
- **Nightly Security Scans**: Automatic execution at 2 AM
- **Multiple Scan Types**: Full, quick, rootkit-only, integrity-only
- **Environment Targeting**: Production, development, Raspberry Pi specific
- **Parallel Execution**: Configurable concurrent host scanning

### 📊 Comprehensive Reporting
- **Real-time Dashboards**: HTML dashboards with drill-down capabilities
- **Email Notifications**: Automated alerts with severity-based routing
- **Slack Integration**: Critical and high-priority finding notifications
- **Historical Tracking**: Trend analysis and compliance reporting

## Quick Start

### 1. Deploy Security Tools

```bash
cd /home/mhiland/Projects/HomeLab/ansible
ansible-playbook playbooks/deploy_security_monitoring.yml -i inventories/homelab
```

### 2. Configure Jenkins Pipeline

1. Create a new Jenkins Pipeline job
2. Point to: `jenkins/security-scanning/Jenkinsfile`
3. Configure credentials:
   - `security-team-email`: Email recipients for notifications
   - SSH keys for Ansible access

### 3. Run Your First Scan

**Manual Execution:**
```bash
# Full security scan on all hosts
ansible-playbook playbooks/security_scan_full.yml

# Quick scan on Raspberry Pi hosts only
ansible-playbook playbooks/security_scan_quick.yml --limit raspberry_pi
```

**Jenkins Pipeline:**
- Navigate to your Jenkins job
- Click "Build with Parameters"
- Select scan type and target environment
- Click "Build"

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SCAN_TYPE` | Type of scan (full/quick/rootkit-only/integrity-only) | full |
| `TARGET_ENVIRONMENT` | Target hosts (all/production/development/raspberry-pi) | all |
| `MAX_PARALLEL_HOSTS` | Maximum concurrent scans | 4 |
| `FORCE_UPDATE_DATABASES` | Update security databases before scanning | false |

### Security Tool Configuration

#### RKhunter
- **Configuration**: `ansible/roles/rkhunter/defaults/main.yml`
- **Scan Frequency**: Daily
- **Reports**: `/var/lib/rkhunter/reports/`

#### AIDE
- **Configuration**: `ansible/roles/aide/defaults/main.yml`
- **Database**: `/var/lib/aide/aide.db`
- **Reports**: `/var/lib/aide/reports/`

#### Chkrootkit
- **Configuration**: `ansible/roles/chkrootkit/defaults/main.yml`
- **Scan Frequency**: Daily
- **Reports**: `/var/lib/chkrootkit/reports/`

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Jenkins       │    │     Ansible      │    │   Target Hosts  │
│   Pipeline      │───▶│   Playbooks      │───▶│   Security      │
│                 │    │                  │    │   Tools         │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Report        │    │   Security       │    │   Log           │
│   Generation    │    │   Analysis       │    │   Collection    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Scan Types

### 1. Full Scan (Recommended for Nightly)
- RKhunter rootkit detection
- Chkrootkit scanning
- AIDE file integrity check
- Package verification (debsums)
- System security assessment

### 2. Quick Scan
- Essential rootkit checks
- Critical file integrity verification
- Minimal system impact

### 3. Rootkit-Only Scan
- RKhunter scanning
- Chkrootkit scanning
- Focused on malware detection

### 4. Integrity-Only Scan
- AIDE file integrity monitoring
- Package verification
- Configuration drift detection

## Notification Configuration

### Email Notifications
- **Recipients**: Configured via Jenkins credentials
- **Triggers**: Critical/High findings or scan failures
- **Content**: Executive summary with detailed reports attached

### Slack Integration
- **Channel**: `#security-alerts`
- **Triggers**: Critical and high-priority findings
- **Format**: Formatted messages with build links

## Security Best Practices

### 1. Access Control
- Jenkins pipeline restricted to security team
- Ansible vault for sensitive configurations
- SSH key-based authentication only

### 2. Data Protection
- Reports encrypted at rest
- Secure transmission of scan results
- Automatic cleanup of temporary files

### 3. Monitoring
- Pipeline execution monitoring
- Failed scan alerting
- Historical trend analysis

## Troubleshooting

### Common Issues

#### 1. Ansible Connection Failures
```bash
# Test connectivity
ansible all -m ping -i inventories/homelab

# Check SSH key permissions
ls -la ~/.ssh/
```

#### 2. Security Tool Installation Failures
```bash
# Check package repositories
ansible all -m shell -a "apt update" -i inventories/homelab

# Verify available packages
ansible all -m shell -a "apt-cache search rkhunter" -i inventories/homelab
```

#### 3. Permission Errors
```bash
# Ensure proper sudo configuration
ansible all -m shell -a "sudo whoami" -i inventories/homelab
```

### Debug Mode

Enable detailed logging in playbooks:
```bash
ansible-playbook playbooks/deploy_security_monitoring.yml -vvv
```

## Monitoring and Maintenance

### Daily Tasks
- ✅ Review automated scan results
- ✅ Investigate critical and high findings
- ✅ Update security tool databases

### Weekly Tasks
- 🔍 Analyze security trends
- 📊 Review false positive rates
- 🔧 Tune security tool configurations

### Monthly Tasks
- 📈 Generate compliance reports
- 🔄 Update security tool versions
- 📋 Review and update exclusions

## Support

### Documentation
- **Ansible Roles**: Individual role README files in `ansible/roles/*/`
- **Jenkins Pipeline**: Comments and documentation within Jenkinsfile
- **Security Tools**: Official documentation links in role configurations

### Logs
- **Jenkins**: Build console output and archived artifacts
- **Ansible**: Execution logs in `/var/log/ansible/`
- **Security Tools**: Individual tool logs in `/var/log/{tool-name}/`

### Contact
- **Security Team**: Configure email notifications
- **System Issues**: Check Jenkins build logs and Ansible output
- **False Positives**: Update exclusion lists in role configurations

---

**Last Updated**: Generated by HomeLab Security Pipeline
**Version**: 1.0.0