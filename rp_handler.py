import runpod
import requests
import websocket  # pip install websocket-client
import json
import uuid
import base64
import os
import time
import shutil

# =================================================================
# CONFIGURATION
# =================================================================
SERVER_ADDRESS = "127.0.0.1:8188"
INPUT_DIR = "/ComfyUI/input"
OUTPUT_DIR = "/ComfyUI/output"

# =================================================================
# SECURITY & FILESYSTEM HELPERS
# =================================================================
def secure_delete(path):
    """
    Overwrites a file with zero-bytes before deleting it.
    Ensures data cannot be recovered from the RAM disk.
    """
    if os.path.exists(path):
        try:
            file_size = os.path.getsize(path)
            with open(path, "wb") as f:
                f.write(b'\0' * file_size)
                f.flush()
                os.fsync(f.fileno())
            os.remove(path)
        except Exception as e:
            print(f"⚠️ Secure delete error for {path}: {e}")

def clear_directory(path):
    """
    Securely wipes all files in the given directory.
    """
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
    Submits the workflow, tracks progress via WebSocket, and returns 
    the list of generated filenames.
    Includes RETRY logic for the History API to prevent race conditions.
    """
    prompt_id = ""
    output_images = {}
    
    # 1. Submit the Workflow to ComfyUI
    p = {"prompt": prompt, "client_id": client_id}
    try:
        response = requests.post(f"http://{SERVER_ADDRESS}/prompt", json=p)
        response.raise_for_status()
        response_data = response.json()
    except Exception as e:
        raise Exception(f"Failed to connect to ComfyUI: {e}")
    
    if 'prompt_id' not in response_data:
        raise Exception(f"ComfyUI Error: {response_data.get('error', 'Unknown Error')}")
        
    prompt_id = response_data['prompt_id']
    
    # 2. Monitor WebSocket for Progress and Completion
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            
            # Send progress updates to RunPod
            if message['type'] == 'progress':
                data = message['data']
                current_step = data['value']
                max_step = data['max']
                runpod.serverless.progress_update(job, f"Step {current_step}/{max_step}")

            # Check if execution finished
            if message['type'] == 'executing':
                data = message['data']
                if data['node'] is None and data['prompt_id'] == prompt_id:
                    break # Execution Finished!
        else:
            continue

    # 3. Retrieve History (With Retry Strategy)
    # The History API is not always instantly populated after the WS message.
    # We retry up to 5 times (1 second total wait) to ensure we get the data.
    history = {}
    for i in range(5):
        try:
            history_resp = requests.get(f"http://{SERVER_ADDRESS}/history/{prompt_id}")
            if history_resp.status_code == 200:
                history_data = history_resp.json()
                if prompt_id in history_data:
                    history = history_data[prompt_id]
                    break
        except Exception:
            pass
        
        # Wait before retrying (backoff)
        print(f"⏳ Waiting for History API... ({i+1}/5)")
        time.sleep(0.2)

    if not history:
        raise Exception(f"Failed to retrieve job history for {prompt_id}. The job finished, but ComfyUI didn't save the metadata in time.")
    
    # 4. Extract filenames from history
    for node_id in history.get('outputs', {}):
        node_output = history['outputs'][node_id]
        if 'images' in node_output:
            for image in node_output['images']:
                output_images[image['filename']] = image['subfolder']
                
    return output_images

# =================================================================
# MAIN HANDLER
# =================================================================
def handler(job):
    job_input = job["input"]
    debug_mode = job_input.get("debug", False)
    
    # 1. Input Validation
    if "workflow" not in job_input:
        return {"status": "error", "message": "Missing 'workflow' in input payload."}
    
    client_id = str(uuid.uuid4())
    ws = websocket.WebSocket()
    
    try:
        # 2. Connection Setup
        ws.connect(f"ws://{SERVER_ADDRESS}/ws?clientId={client_id}")
        
        # Only clear directories if we aren't debugging
        if not debug_mode:
            clear_directory(INPUT_DIR)
            clear_directory(OUTPUT_DIR)
        
        # 3. Decode Input Images (Base64 -> RAM Disk)
        # CRITICAL: We use fsync to ensure the OS writes to RAM immediately
        if "images" in job_input and isinstance(job_input["images"], dict):
            for filename, b64_str in job_input["images"].items():
                file_path = os.path.join(INPUT_DIR, filename)
                with open(file_path, "wb") as f:
                    f.write(base64.b64decode(b64_str))
                    f.flush()            # Force Python buffer write
                    os.fsync(f.fileno()) # Force OS disk write
                    
        # 4. Execute Workflow
        workflow = job_input["workflow"]
        output_files = get_images(ws, workflow, client_id, job)
        
        # 5. Encode Output Images (RAM Disk -> Base64)
        result_images = {}
        
        # CRITICAL: Tiny sleep to ensure ComfyUI has fully released file handles
        time.sleep(0.1)
        
        for filename in output_files:
            file_path = os.path.join(OUTPUT_DIR, filename)
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode('utf-8')
                    result_images[filename] = encoded
            else:
                print(f"⚠️  Expected output file missing: {filename}")

        return {"status": "success", "images": result_images}

    except Exception as e:
        print(f"❌ Handler Error: {str(e)}")
        return {"status": "error", "message": str(e)}
        
    finally:
        # 6. Cleanup
        try:
            ws.close()
        except:
            pass
            
        if debug_mode:
            print(f"⚠️ DEBUG MODE: Files left in {INPUT_DIR} and {OUTPUT_DIR}")
        else:
            clear_directory(INPUT_DIR)
            clear_directory(OUTPUT_DIR)

if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
