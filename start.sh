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

        if [ ! -f /etc/ssh/ssh_host_ed25519_key ]; then
            ssh-keygen -t ed25519 -f /etc/ssh/ssh_host_ed25519_key -q -N ''
        fi
        
        mkdir -p /run/sshd
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
cd /ComfyUI
source .venv/bin/activate
python3 utils.py

# =================================================================
# 3. SECURE RAM DISK SETUP
# =================================================================
echo "---------------------------------------------------"
echo "🛡️  Setting up Secure Input/Output in /dev/shm"
echo "---------------------------------------------------"

# Remove default persistent directories if they exist
rm -rf /ComfyUI/input
rm -rf /ComfyUI/output

# Create RAM disk directories
mkdir -p /dev/shm/input
mkdir -p /dev/shm/output

# Link them back to ComfyUI
# ComfyUI writes to ./input, but it actually goes to RAM
ln -s /dev/shm/input /ComfyUI/input
ln -s /dev/shm/output /ComfyUI/output

echo "✅ /ComfyUI/input  -> /dev/shm/input"
echo "✅ /ComfyUI/output -> /dev/shm/output"

# =================================================================
# 4. LAUNCH COMFYUI (BACKGROUND)
# =================================================================
echo "---------------------------------------------------"
echo "🚀 Launching ComfyUI Server..."
echo "---------------------------------------------------"

setup_ssh

# Start ComfyUI in background (&)
# --listen 127.0.0.1: Only accessible to localhost (secure)
# --port 8188: Standard port
# --fast: Optimizations
# --use-pytorch-cross-attention: Force standard optimized attention
python3 main.py --listen 127.0.0.1 --port 8188 --fast --use-pytorch-cross-attention > /dev/null 2>&1 &
COMFY_PID=$!

# Wait for Server to be ready (Health Check)
echo "⏳ Waiting for ComfyUI to become responsive..."
while ! curl -s http://127.0.0.1:8188 > /dev/null; do
    sleep 1
done
echo "✅ ComfyUI is Alive!"

# =================================================================
# 5. START SERVERLESS HANDLER
# =================================================================
echo "---------------------------------------------------"
echo "🎧 Starting RunPod Handler..."
echo "---------------------------------------------------"

# This script blocks and processes incoming jobs
python3 rp_handler.py
