# Jenkins Job Configuration Examples

> **⚠️ IMPORTANT: This is a template document**
> 
> All usernames, hostnames, IP addresses, and infrastructure details in this document are **generic examples** that must be customized for your specific environment. Replace placeholder values like `your-username`, `pi1`, `your-ssh-credential-id` with your actual infrastructure details before using these configurations.

This document provides configuration examples for using the Jenkins Ansible Plugin with the HomeLab patching playbooks.

## Prerequisites

1. **Install Jenkins Ansible Plugin**
   - Go to Jenkins → Manage Jenkins → Manage Plugins
   - Install "Ansible" plugin
   - Restart Jenkins

2. **Configure Ansible Installation**
   - Go to Jenkins → Manage Jenkins → Global Tool Configuration
   - Add Ansible installation (auto-install or specify path)

3. **Configure SSH Credentials**
   - Go to Jenkins → Manage Jenkins → Manage Credentials
   - Add SSH private key credential for accessing remote hosts
   - Note the credential ID for job configuration

## Daily Patching Job Configuration

### Freestyle Job Setup

1. **Create New Job**
   - New Item → Freestyle project
   - Name: `HomeLab-Daily-Patching`

2. **General Configuration**
   - Description: `Daily safe upgrades for HomeLab infrastructure`
   - Restrict execution to nodes with label: `master` (or appropriate node)

3. **Build Triggers**
   - Build periodically: `H 2 * * *` (daily at 2 AM)

4. **Build Environment**
   - Set environment variables:
     ```
     ANSIBLE_HOST_KEY_CHECKING=False
     ANSIBLE_STDOUT_CALLBACK=yaml
     ```

5. **Build Steps**
   - Add build step: "Invoke Ansible Playbook"
   - Configure as follows:

   ```yaml
   Playbook path: ansible/playbooks/patch_systems_nightly.yml
   Inventory: 
     - Inline: |
         [homelab]
         pi1 ansible_user=your-username
         pi2 ansible_user=your-username
         pi3 ansible_user=your-username
         # Add additional hosts as needed
   Credentials: your-ssh-credential-id  # Replace with your SSH credential ID
   Host Key Checking: Unchecked
   Become: Checked
   Become User: root
   Extra Variables:
     - Key: serial_percentage, Value: 100
     - Key: log_directory, Value: ${WORKSPACE}/ansible_logs
   ```

6. **Post-build Actions**
   - Archive artifacts: `ansible_logs/**/*.md`
   - Publish build scan results (if desired)

### Pipeline Job Setup (Recommended)

Create a new Pipeline job with the following Jenkinsfile:

```groovy
pipeline {
    agent any
    
    environment {
        ANSIBLE_HOST_KEY_CHECKING = 'False'
        ANSIBLE_STDOUT_CALLBACK = 'yaml'
    }
    
    parameters {
        choice(
            name: 'TARGET_HOSTS',
            choices: ['all', 'pi1', 'pi2', 'pi3'],  // Replace with your actual hostnames
            description: 'Select target hosts'
        )
        choice(
            name: 'SERIAL_PERCENTAGE', 
            choices: ['100', '50', '25'],
            description: 'Parallel execution percentage'
        )
    }
    
    stages {
        stage('Daily Patching') {
            steps {
                script {
                    // Customize this inventory section with your actual hosts and username
                    def inventory = """
                    [homelab]
                    pi1 ansible_user=your-username
                    pi2 ansible_user=your-username
                    pi3 ansible_user=your-username
                    # Add additional hosts as needed
                    """
                    
                    def limit = params.TARGET_HOSTS == 'all' ? '' : params.TARGET_HOSTS
                    
                    ansiblePlaybook(
                        playbook: 'ansible/playbooks/patch_systems_nightly.yml',
                        inventory: inventory,
                        credentialsId: 'your-ssh-credential-id',  // Replace with your SSH credential ID
                        limit: limit,
                        become: true,
                        becomeUser: 'root',
                        extraVars: [
                            serial_percentage: params.SERIAL_PERCENTAGE,
                            log_directory: "${WORKSPACE}/ansible_logs"
                        ]
                    )
                }
            }
        }
    }
    
    post {
        always {
            archiveArtifacts artifacts: 'ansible_logs/**/*.md', allowEmptyArchive: true
        }
        success {
            echo 'Daily patching completed successfully!'
        }
        failure {
            echo 'Daily patching failed. Check logs for details.'
        }
    }
}
```

## Monthly Full Upgrade Job Configuration

### Freestyle Job Setup

Similar to daily patching but with these differences:

1. **Job Name**: `HomeLab-Monthly-Upgrade`
2. **Description**: `Monthly full system upgrades for HomeLab infrastructure`
3. **Build Triggers**: `H 3 1 * *` (monthly on 1st at 3 AM)
4. **Playbook path**: `ansible/playbooks/patch_systems_monthly.yml`

### Pipeline Job Setup

```groovy
pipeline {
    agent any
    
    environment {
        ANSIBLE_HOST_KEY_CHECKING = 'False'
        ANSIBLE_STDOUT_CALLBACK = 'yaml'
    }
    
    parameters {
        choice(
            name: 'TARGET_HOSTS',
            choices: ['all', 'pi1', 'pi2', 'pi3'],  // Replace with your actual hostnames
            description: 'Select target hosts'
        )
        booleanParam(
            name: 'CONFIRM_UPGRADE',
            defaultValue: false,
            description: 'Confirm you want to perform full system upgrade'
        )
    }
    
    stages {
        stage('Confirmation') {
            when {
                not { params.CONFIRM_UPGRADE }
            }
            steps {
                error('Monthly upgrade requires confirmation. Please check CONFIRM_UPGRADE parameter.')
            }
        }
        
        stage('Monthly Full Upgrade') {
            steps {
                script {
                    // Customize this inventory section with your actual hosts and username
                    def inventory = """
                    [homelab]
                    pi1 ansible_user=your-username
                    pi2 ansible_user=your-username
                    pi3 ansible_user=your-username
                    # Add additional hosts as needed
                    """
                    
                    def limit = params.TARGET_HOSTS == 'all' ? '' : params.TARGET_HOSTS
                    
                    ansiblePlaybook(
                        playbook: 'ansible/playbooks/patch_systems_monthly.yml',
                        inventory: inventory,
                        credentialsId: 'your-ssh-credential-id',  // Replace with your SSH credential ID
                        limit: limit,
                        become: true,
                        becomeUser: 'root',
                        extraVars: [
                            serial_percentage: '50',  // More conservative for full upgrades
                            log_directory: "${WORKSPACE}/ansible_logs"
                        ]
                    )
                }
            }
        }
    }
    
    post {
        always {
            archiveArtifacts artifacts: 'ansible_logs/**/*.md', allowEmptyArchive: true
        }
        success {
            echo 'Monthly full upgrade completed successfully!'
        }
        failure {
            echo 'Monthly full upgrade failed. Check logs for details.'
        }
    }
}
```

## Advanced Configuration Options

### Dynamic Inventory from Parameters

For more flexible host management:

```groovy
parameters {
    string(
        name: 'REMOTE_SERVERS',
        defaultValue: 'pi1,pi2,pi3',  // Replace with your actual server hostnames
        description: 'Comma-separated list of target servers'
    )
    string(
        name: 'REMOTE_USER',
        defaultValue: 'your-username',  // Replace with your SSH username
        description: 'SSH username for remote connections'
    )
}

script {
    def servers = params.REMOTE_SERVERS.split(',')
    def inventory = "[homelab]\n"
    servers.each { server ->
        inventory += "${server.trim()} ansible_user=${params.REMOTE_USER}\n"
    }
    
    ansiblePlaybook(
        playbook: 'ansible/playbooks/patch_systems_nightly.yml',
        inventory: inventory,
        credentialsId: 'your-ssh-credential-id',  // Replace with your SSH credential ID
        // ... rest of configuration
    )
}
```

### Parallel Execution Control

```groovy
parameters {
    choice(
        name: 'EXECUTION_STRATEGY',
        choices: ['parallel', 'serial', 'rolling'],
        description: 'Execution strategy'
    )
}

script {
    def serialPercentage = '100'
    switch(params.EXECUTION_STRATEGY) {
        case 'serial':
            serialPercentage = '1'
            break
        case 'rolling':
            serialPercentage = '50'
            break
        case 'parallel':
        default:
            serialPercentage = '100'
            break
    }
    
    // Use serialPercentage in extraVars
}
```

### Notification Setup

Add to pipeline post actions:

```groovy
post {
    success {
        slackSend(
            channel: '#your-channel',  // Replace with your Slack channel
            color: 'good',
            message: "✅ ${env.JOB_NAME} #${env.BUILD_NUMBER} completed successfully"
        )
    }
    failure {
        slackSend(
            channel: '#your-channel',  // Replace with your Slack channel
            color: 'danger',
            message: "❌ ${env.JOB_NAME} #${env.BUILD_NUMBER} failed. Check logs: ${env.BUILD_URL}"
        )
    }
}
```

## Testing and Validation

### Dry Run Configuration

Add a parameter for dry run testing:

```groovy
parameters {
    booleanParam(
        name: 'DRY_RUN',
        defaultValue: false,
        description: 'Perform dry run (check mode)'
    )
}

ansiblePlaybook(
    // ... other configuration
    check: params.DRY_RUN,
    diff: true
)
```

### Single Host Testing

Always test with a single host first:

```groovy
stage('Single Host Test') {
    when {
        params.TARGET_HOSTS == 'all'
    }
    steps {
        input message: 'Test on single host first?', ok: 'Proceed with pi1 only'  // Replace pi1 with your test host
        
        ansiblePlaybook(
            // ... configuration
            limit: 'pi1'  // Replace with your test hostname
        )
        
        input message: 'Single host test completed. Continue with all hosts?', ok: 'Continue'
    }
}
```

## Customization Checklist

Before using these Jenkins job templates, ensure you customize the following placeholders:

### Required Replacements
- **`your-username`** → Your SSH username for connecting to remote hosts
- **`pi1`, `pi2`, `pi3`** → Your actual server hostnames or IP addresses
- **`your-ssh-credential-id`** → The ID of your SSH private key credential in Jenkins
- **`#your-channel`** → Your Slack channel for notifications (if using Slack integration)

### Optional Customizations
- **Job names** → Adjust `HomeLab-Daily-Patching` and `HomeLab-Monthly-Upgrade` to match your naming conventions
- **Schedule triggers** → Modify cron expressions (`H 2 * * *`, `H 3 1 * *`) for your preferred maintenance windows
- **Serial percentage** → Adjust parallel execution settings based on your infrastructure size and requirements
- **Notification channels** → Configure email, Slack, or other notification methods as needed

### Environment-Specific Settings
- **Inventory groups** → Modify `[homelab]` group name to match your Ansible inventory structure
- **Additional hosts** → Add more servers to the inventory sections as needed
- **Extra variables** → Add environment-specific variables as required by your playbooks

### Security Considerations
- Ensure SSH credentials are properly configured in Jenkins credential store
- Test with a single host before running against your entire infrastructure
- Use appropriate serial percentages to avoid overloading your network or systems