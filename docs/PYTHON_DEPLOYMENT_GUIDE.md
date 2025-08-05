# Python Management Deployment Guide

> **Note**: All hostnames in this document (pi1, pi2, pi3, etc.) are generic examples. Replace them with your actual infrastructure hostnames when using these commands.

## Overview
This guide implements explicit Python version management across the HomeLab cluster using **standardized symlinks** at `/opt/python3.11/` pointing to system Python. This provides path consistency without compilation overhead.

## Deployment Steps

### 1. Deploy Managed Python (First Time)
```bash
# Deploy standardized Python symlinks to all hosts (fast - takes ~30 seconds)
ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/deploy_python_management.yml

# Test single host first if desired (replace 'pi1' with your target host)
ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/deploy_python_management.yml --limit pi1
```

### 2. Test Connectivity with Managed Python
```bash
# Test that Ansible can connect using the new interpreter
# Note: The inventory has already been updated to use /opt/python3.11/bin/python3
ansible all -i ansible/inventories/homelab/hosts -m ping

# Test Python version consistency
ansible all -i ansible/inventories/homelab/hosts -m command -a "/opt/python3.11/bin/python3 --version"
```

### 3. Run Patching Jobs with Version Enforcement
```bash
# Nightly patching with Python version enforcement
ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/patch_systems_nightly.yml

# Monthly patching with Python version enforcement  
ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/patch_systems_monthly.yml
```

## Version Enforcement Behavior

### Progressive Execution with End Failures
- **Each host progresses as far as possible** - one failing host doesn't block others
- **Python compliance checks run early** but only collect issues (no immediate failure)
- **Patching work completes** on all hosts regardless of Python compliance
- **Hard failures occur at the end** after all hosts complete their work

### Benefits
- Maximum progress on healthy hosts
- Complete visibility into all compliance issues across the cluster
- Patching work gets done even when some hosts have Python issues
- Clear end-of-job reporting with actionable next steps

### Error Messages
```
Python compliance check - pi2:
✗ NON-COMPLIANT - Issues found:
- Missing managed Python at /opt/python3.11/bin/python3

CRITICAL: Python compliance failures detected on pi2

Issues found:
- Missing managed Python at /opt/python3.11/bin/python3

Actions required:
1. Run deploy_python_management.yml playbook to install/fix Python
2. Verify Python installation: /opt/python3.11/bin/python3 --version
3. Re-run patching job after compliance is restored

This host has completed patching but system state may be inconsistent.
```

## Rollback Plan
If issues occur:
```bash
# Temporarily revert to system Python (emergency only)
# Edit ansible/inventories/homelab/group_vars/all.yml:
ansible_python_interpreter: /usr/bin/python3

# Test connectivity
ansible all -i ansible/inventories/homelab/hosts -m ping

# Redeploy managed Python when ready
ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/deploy_python_management.yml
```

## Files Created/Modified

### New Files
- `ansible/roles/python_management/` - Complete role for Python 3.11 management
- `ansible/playbooks/deploy_python_management.yml` - Deployment playbook
- `PYTHON_DEPLOYMENT_GUIDE.md` - This guide

### Modified Files
- `ansible/inventories/homelab/group_vars/all.yml` - Updated interpreter path
- `ansible/playbooks/patch_systems_nightly.yml` - Added version enforcement
- `ansible/playbooks/patch_systems_monthly.yml` - Added version enforcement

## Expected Results

### After Deployment
- Standardized Python symlinks at `/opt/python3.11/bin/python3` on all hosts
- Path consistency for Ansible operations across entire cluster  
- Patching jobs protected with version enforcement
- Clear error messages for any configuration drift

### System Impact
- System Python remains untouched (rollback safety)
- Managed Python added to system PATH via symlinks
- Minimal disk usage (~1KB per host for symlinks)
- Deployment completes in seconds, not hours

### Current Cluster State (Example)
- pi1, pi3: Python 3.11.2 via symlink
- pi2: Python 3.13.3 via symlink  
- All hosts: Working managed Python at `/opt/python3.11/bin/python3`

**Note**: Replace example hostnames (pi1, pi2, pi3) with your actual host names.

## Maintenance

### Upgrading Python Version
1. Update `python_version` in `ansible/roles/python_management/defaults/main.yml`
2. Run deployment playbook to install new version
3. Update version enforcement checks in patching playbooks
4. Test thoroughly before deploying to production

### Monitoring
- Patching jobs will automatically detect and report version drift
- Check logs for Python compliance verification messages
- Monitor disk usage in `/opt/` partition

## Troubleshooting

### Common Issues

#### Role Not Found Error
```
[ERROR]: the role 'python_management' was not found
```
**Solution**: Always include `ANSIBLE_ROLES_PATH=ansible/roles` in commands:
```bash
ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts ansible/playbooks/deploy_python_management.yml
```

#### Log Directory Permission Error
```
[ERROR]: There was an issue creating /python_deployment
```
**Solution**: This was fixed in the deployment playbook. Update to latest version.

#### Disk Space Check Fails with Adequate Space
```
[ERROR]: Insufficient disk space in /opt: 97G
```
**Solution**: This was fixed in the deployment playbook logic. Update to latest version.

#### Connectivity Test Fails
```
/bin/sh: 1: /opt/python3.11/bin/python3: not found
```
**Solution**: 
1. Deploy managed Python first: `ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook ... deploy_python_management.yml`
2. Then update inventory to use managed Python

### Verification Commands
```bash
# Check if symlinks exist on all hosts
ansible raspberrypi -i ansible/inventories/homelab/hosts -m shell -a "ls -la /opt/python3.11/bin/"

# Test managed Python works
ansible raspberrypi -i ansible/inventories/homelab/hosts -m shell -a "/opt/python3.11/bin/python3 --version"

# Test Ansible connectivity
ansible all -i ansible/inventories/homelab/hosts -m ping

# Check disk space
ansible raspberrypi -i ansible/inventories/homelab/hosts -m shell -a "df -h /opt"
```