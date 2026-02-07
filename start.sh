# =================================================================
# 4. LAUNCH COMFYUI (BACKGROUND)
# =================================================================
echo "---------------------------------------------------"
echo "🚀 Launching ComfyUI Server..."
echo "---------------------------------------------------"

setup_ssh

# Create a log file and start tailing it in the background so you see logs immediately
touch /ComfyUI/comfyui.log
tail -f /ComfyUI/comfyui.log &
TAIL_PID=$!

# Start ComfyUI
# We redirect both stdout and stderr to the log file
python3 main.py --listen 127.0.0.1 --port 8188 --fast --use-pytorch-cross-attention > /ComfyUI/comfyui.log 2>&1 &
COMFY_PID=$!

# Wait for Server to be ready using curl
echo "⏳ Waiting for ComfyUI to become responsive on localhost:8188..."
MAX_RETRIES=120 # Increased to 2 minutes for slow model loading
COUNT=0

while ! curl -s http://127.0.0.1:8188 > /dev/null; do
    sleep 2
    ((COUNT+=2))
    
    if [ $COUNT -ge $MAX_RETRIES ]; then
        echo "❌ ERROR: ComfyUI failed to start within $MAX_RETRIES seconds."
        kill $TAIL_PID
        exit 1
    fi
done

# Kill the background tail process once we are alive so it doesn't clutter the handler logs
kill $TAIL_PID
echo "✅ ComfyUI is Alive!"

# =================================================================
# 5. START SERVERLESS HANDLER OR INTERACTIVE MODE
# =================================================================
echo "---------------------------------------------------"
if [ "$MODE" == "interactive" ]; then
    echo "🎧 Interactive Mode Detected. Sleeping indefinitely..."
    sleep infinity
else
    echo "🎧 Starting RunPod Handler..."
    python3 rp_handler.py
fi
