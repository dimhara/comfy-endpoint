#!/bin/bash

# =================================================================
# 1. SSH SETUP
# =================================================================
setup_ssh() {
    if [[ $PUBLIC_KEY ]]; then
        echo "🔒 Setting up SSH..."
        mkdir -p ~/.ssh
        echo "$PUBLIC_KEY" >> ~/.ssh/authorized_keys
        chmod 700 -R ~/.ssh

        # Generate host keys if they don't exist
        if [ ! -f /etc/ssh/ssh_host_ed25519_key ]; then
            ssh-keygen -t ed25519 -f /etc/ssh/ssh_host_ed25519_key -q -N ''
        fi
        
        # Ensure directory exists for privilege separation
        mkdir -p /run/sshd
        
        # Start SSH Daemon in the background
        /usr/sbin/sshd
        echo "✅ SSH server is running."
    else
        echo "⚠️  No PUBLIC_KEY environment variable found. SSH access will be disabled."
    fi
}

# =================================================================
# 2. MODEL PREPARATION
# =================================================================
echo "---------------------------------------------------"
echo "📥 Syncing Models via utils.py..."
echo "---------------------------------------------------"

# Navigate to application directory
cd /ComfyUI

# Activate the virtual environment
source .venv/bin/activate

# Run the utility script to download or link models
# This ensures that even if the image isn't 'baked', the models 
# are fetched before the UI starts.
python3 utils.py

# =================================================================
# 3. LAUNCH COMFYUI
# =================================================================
echo "---------------------------------------------------"
echo "🚀 Launching ComfyUI..."
echo "---------------------------------------------------"

# Initialize SSH
setup_ssh

# Execute ComfyUI
# --listen 0.0.0.0: Required to allow RunPod's proxy to reach the container
# --port 8188: Standard ComfyUI port
# 'exec' replaces the shell process with the python process (PID 1)
exec python3 main.py --listen 127.0.0.1 --port 8000
