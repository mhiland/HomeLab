#!/bin/bash

# This script must run as root initially to set up /run directory
# Then it calls the original setup-sshd which handles user switching

# Ensure we're root for initial setup
if [ "$(id -u)" = "0" ]; then
    # Ensure /run directory exists and is writable for sshd pid file
    mkdir -p /run
    chmod 755 /run
    
    # Make sure /run persists by creating it in a way that survives the container lifecycle
    # Also ensure sshd can write to it
    chown root:root /run
    
    # Create symlink for Java in /usr/bin for Jenkins compatibility
    if [ -f /opt/java/openjdk/bin/java ] && [ ! -f /usr/bin/java ]; then
        ln -s /opt/java/openjdk/bin/java /usr/bin/java
    fi
    
    # Append algorithm configuration to sshd_config to exclude sk-* algorithms
    if ! grep -q "HostKeyAlgorithms" /etc/ssh/sshd_config; then
        echo "" >> /etc/ssh/sshd_config
        echo "# Custom algorithm configuration to exclude sk-* algorithms" >> /etc/ssh/sshd_config
        echo "HostKeyAlgorithms ssh-ed25519,ecdsa-sha2-nistp256,ecdsa-sha2-nistp384,ecdsa-sha2-nistp521,rsa-sha2-512,rsa-sha2-256,ssh-rsa" >> /etc/ssh/sshd_config
        echo "PubkeyAcceptedKeyTypes ssh-ed25519,ecdsa-sha2-nistp256,ecdsa-sha2-nistp384,ecdsa-sha2-nistp521,rsa-sha2-512,rsa-sha2-256,ssh-rsa" >> /etc/ssh/sshd_config
    fi
fi

# Call the original jenkins/ssh-agent entrypoint
# This will handle switching to jenkins user for the SSH key setup
# but sshd itself will run as root (as it needs to)
exec /usr/local/bin/setup-sshd "$@"