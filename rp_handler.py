import runpod
import requests
import websocket  # pip install websocket-client
import json
import uuid
import base64
import os
import time
from cryptography.fernet import Fernet

# =================================================================
# CONFIGURATION & SECURITY
# =================================================================
SERVER_ADDRESS = "127.0.0.1:8188"
INPUT_DIR = "/ComfyUI/input"
OUTPUT_DIR = "/ComfyUI/output"

# Standardizing with ENCRYPTION_KEY env var
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")
cipher = Fernet(ENCRYPTION_KEY.encode()) if ENCRYPTION_KEY else None

# =================================================================
# SECURITY & FILESYSTEM HELPERS
# =================================================================
def secure_delete(path):
    """Overwrites a file with zeros before deleting it (RAM disk safety)."""
    if os.path.exists(path):
        try:
            file_size = os.path.getsize(path)
            with open(path, "wb") as f:
                f.write(b'\0' * file_size)
                f.flush()
                os.fsync(f.fileno())
            os.remove(path)
        except Exception as e:
            print(f"⚠️ Secure delete error: {e}")

def clear_directory(path):
    """Securely wipes all files in the given directory."""
    if os.path.exists(path):
        for f in os.listdir(path):
            file_path = os.path.join(path, f)
            if os.path.isfile(file_path):
                secure_delete(file_path)

# =================================================================
# COMFYUI API LOGIC
# =================================================================
def get_images(ws, prompt, client_id, job):
    """
    Submits workflow and monitors progress.
    FIX: Includes a retry loop for History API to prevent race conditions.
    """
    # 1. Submit Prompt
    p = {"prompt": prompt, "client_id": client_id}
    response = requests.post(f"http://{SERVER_ADDRESS}/prompt", json=p)
    response.raise_for_status()
    prompt_id = response.json()['prompt_id']
    
    # 2. Monitor WebSocket
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message['type'] == 'progress':
                data = message['data']
                runpod.serverless.progress_update(job, f"Step {data['value']}/{data['max']}")
            if message['type'] == 'executing':
                if message['data']['node'] is None and message['data']['prompt_id'] == prompt_id:
                    break 
        else:
            continue

    # 3. Retrieve History (Retry Loop Fix)
    history = {}
    for i in range(5):
        time.sleep(0.2) # Backoff
        resp = requests.get(f"http://{SERVER_ADDRESS}/history/{prompt_id}")
        if resp.status_code == 200:
            data = resp.json()
            if prompt_id in data:
                history = data[prompt_id]
                break
        print(f"⏳ History API not ready, retry {i+1}/5...")

    if not history:
        raise Exception("Failed to retrieve job metadata from ComfyUI history.")

    # 4. Extract filenames
    output_images = {}
    for node_id in history.get('outputs', {}):
        node_output = history['outputs'][node_id]
        if 'images' in node_output:
            for img in node_output['images']:
                output_images[img['filename']] = img['subfolder']
                
    return output_images

# =================================================================
# MAIN HANDLER
# =================================================================
def handler(job):
    job_input = job["input"]
    is_encrypted = job_input.get("is_encrypted", False)
    debug_mode = job_input.get("debug", False)
    
    # 1. Decryption Layer
    try:
        if is_encrypted:
            if not cipher:
                return {"status": "error", "message": "Server missing ENCRYPTION_KEY."}
            
            print("🔓 Decrypting internal payload...")
            decrypted_data = cipher.decrypt(job_input["encrypted_input"].encode()).decode()
            inner_payload = json.loads(decrypted_data)
            
            workflow = inner_payload.get("workflow")
            images_dict = inner_payload.get("images", {})
        else:
            # Debug/Plaintext Mode
            workflow = job_input.get("workflow")
            images_dict = job_input.get("images", {})
            
    except Exception as e:
        return {"status": "error", "message": f"Decryption failed: {str(e)}"}

    if not workflow:
        return {"status": "error", "message": "No workflow provided."}

    client_id = str(uuid.uuid4())
    ws = websocket.WebSocket()
    
    try:
        ws.connect(f"ws://{SERVER_ADDRESS}/ws?clientId={client_id}")
        
        if not debug_mode:
            clear_directory(INPUT_DIR)
            clear_directory(OUTPUT_DIR)
        
        # 2. Write Input Images (Race Condition Fix: fsync)
        for filename, b64_str in images_dict.items():
            file_path = os.path.join(INPUT_DIR, filename)
            with open(file_path, "wb") as f:
                f.write(base64.b64decode(b64_str))
                f.flush()
                os.fsync(f.fileno())
                    
        # 3. Execute Workflow
        output_files = get_images(ws, workflow, client_id, job)
        
        # 4. Encode Output Images (Race Condition Fix: Buffer Sleep)
        result_images = {}
        time.sleep(0.1) 
        
        for filename in output_files:
            file_path = os.path.join(OUTPUT_DIR, filename)
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    result_images[filename] = base64.b64encode(f.read()).decode('utf-8')

        return {"status": "success", "images": result_images}

    except Exception as e:
        print(f"❌ Handler Error: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        ws.close()
        if not debug_mode:
            clear_directory(INPUT_DIR)
            clear_directory(OUTPUT_DIR)

if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
