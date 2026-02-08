#!/bin/bash

# =================================================================
# 1. FUNCTION DEFINITIONS (Must be defined before use)
# =================================================================

setup_ssh() {
    if [[ $PUBLIC_KEY ]]; then
        echo "🔒 Setting up SSH..."
        mkdir -p ~/.ssh
        echo "$PUBLIC_KEY" >> ~/.ssh/authorized_keys
        chmod 700 -R ~/.ssh

        # Generate SSH host keys if they don't exist (prevents errors on pod restart)
        if [ ! -f /etc/ssh/ssh_host_ed25519_key ]; then
            ssh-keygen -t ed25519 -f /etc/ssh/ssh_host_ed25519_key -q -N ''
        fi
        
        # Ensure the privilege separation directory exists
        mkdir -p /run/sshd
        
        # Start the SSH Daemon
        /usr/sbin/sshd
        echo "✅ SSH server is running."
    else
        echo "⚠️  No PUBLIC_KEY environment variable found. SSH access disabled."
    fi
}

# =================================================================
# 2. MODEL PREPARATION
# =================================================================
echo "---------------------------------------------------"
echo "📥 Syncing Models via utils.py..."
echo "---------------------------------------------------"

# Navigate to application folder and activate environment
cd /ComfyUI
source .venv/bin/activate

# Use the utility script to download or link models from cache
python3 utils.py

# =================================================================
# 3. SECURE RAM DISK SETUP (Input/Output)
# =================================================================
echo "---------------------------------------------------"
echo "🛡️  Setting up Secure RAM Disk in /dev/shm"
echo "---------------------------------------------------"

# Remove default persistent folders
rm -rf /ComfyUI/input /ComfyUI/output

# Create fresh directories in RAM
mkdir -p /dev/shm/input /dev/shm/output

# Create symlinks so ComfyUI sees them as local folders
ln -s /dev/shm/input /ComfyUI/input
ln -s /dev/shm/output /ComfyUI/output

echo "✅ /ComfyUI/input  -> /dev/shm/input"
echo "✅ /ComfyUI/output -> /dev/shm/output"

# =================================================================
# 4. LAUNCH COMFYUI SERVER
# =================================================================
echo "---------------------------------------------------"
echo "🚀 Launching ComfyUI & SSH Services..."
echo "---------------------------------------------------"

# Start the SSH service
setup_ssh

# Create a log file for startup monitoring
touch /ComfyUI/comfyui.log

# Start ComfyUI in the background
# --listen 127.0.0.1: Only accessible to localhost (secure)
# --fast / --use-pytorch-cross-attention: Optimization flags
# TODO : readd --fast if it works!
python3 main.py --listen 127.0.0.1 --port 8188 --use-pytorch-cross-attention >> /ComfyUI/comfyui.log 2>&1 &
COMFY_PID=$!

# Health Check: Wait for ComfyUI to respond on localhost:8188
echo "⏳ Waiting for ComfyUI to become responsive..."
MAX_RETRIES=60
COUNT=0

while ! curl -s http://127.0.0.1:8188 > /dev/null; do
    # Display the last line of the log to see startup errors or progress
    tail -n 1 /ComfyUI/comfyui.log
    
    sleep 2
    ((COUNT++))
    
    if [ $COUNT -ge $MAX_RETRIES ]; then
        echo "❌ ERROR: ComfyUI failed to start within timeout."
        echo "--- Full Log ---"
        cat /ComfyUI/comfyui.log
        exit 1
    fi
done

echo "✅ ComfyUI is Alive!"

# =================================================================
# 5. START SERVERLESS HANDLER OR INTERACTIVE MODE
# =================================================================
echo "---------------------------------------------------"

if [ "$MODE" == "interactive" ]; then
    echo "🎧 Interactive Mode Detected. ComfyUI is running on localhost:8188."
    echo "   Use SSH tunneling to access: ssh -L 8188:127.0.0.1:8188 root@<IP> -p <PORT>"
    echo "   Keeping container alive..."
    sleep infinity
else
    echo "🎧 Starting RunPod Serverless Handler (rp_handler.py)..."
    # This process will block and handle incoming jobs from RunPod
    python3 rp_handler.py
fi
