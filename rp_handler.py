import runpod
import requests
import websocket
import json
import uuid
import base64
import os
import time

# CONFIGURATION
SERVER_ADDRESS = "127.0.0.1:8188"
INPUT_DIR = "/ComfyUI/input"
OUTPUT_DIR = "/ComfyUI/output"

# =================================================================
# SECURITY & FILESYSTEM HELPERS
# =================================================================
def secure_delete(path):
    """Overwrites a file with zero-bytes before deleting it."""
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
    """Submits workflow and monitors progress via WebSocket."""
    p = {"prompt": prompt, "client_id": client_id}
    response = requests.post(f"http://{SERVER_ADDRESS}/prompt", json=p)
    response_data = response.json()
    
    if 'prompt_id' not in response_data:
        raise Exception(f"ComfyUI Error: {response_data.get('error', 'Unknown Error')}")
        
    prompt_id = response_data['prompt_id']
    
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message['type'] == 'progress':
                data = message['data']
                runpod.serverless.progress_update(job, f"Step {data['value']}/{data['max']}")

            if message['type'] == 'executing':
                data = message['data']
                if data['node'] is None and data['prompt_id'] == prompt_id:
                    break 
        else:
            continue

    history_resp = requests.get(f"http://{SERVER_ADDRESS}/history/{prompt_id}")
    history = history_resp.json().get(prompt_id, {})
    
    output_images = {}
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
    
    if "workflow" not in job_input:
        return {"status": "error", "message": "Missing 'workflow' in input payload."}
    
    workflow = job_input["workflow"]
    client_id = str(uuid.uuid4())
    ws = websocket.WebSocket()
    
    try:
        ws.connect(f"ws://{SERVER_ADDRESS}/ws?clientId={client_id}")
        
        # 1. Clean Directories
        clear_directory(INPUT_DIR)
        clear_directory(OUTPUT_DIR)
        
        # 2. Save Uploaded Images with Fsync (Prevent Race Condition)
        uploaded_files = []
        if "images" in job_input and isinstance(job_input["images"], dict):
            for filename, b64_str in job_input["images"].items():
                file_path = os.path.join(INPUT_DIR, filename)
                with open(file_path, "wb") as f:
                    f.write(base64.b64decode(b64_str))
                    f.flush()            # Force Python to write to OS buffer
                    os.fsync(f.fileno()) # Force OS to write to RAM Disk
                uploaded_files.append(filename)
                print(f"✅ Saved input: {filename} ({os.path.getsize(file_path)} bytes)")

        # 3. Smart Injection: Sync Workflow with Uploaded Filenames
        # We find LoadImage nodes and map them to the files we just saved
        if uploaded_files:
            # Map nodes to files in the order they appear
            load_image_nodes = [id for id, data in workflow.items() if data.get("class_type") == "LoadImage"]
            for i, node_id in enumerate(load_image_nodes):
                if i < len(uploaded_files):
                    target_file = uploaded_files[i]
                    workflow[node_id]["inputs"]["image"] = target_file
                    print(f"🎯 Injection: Node {node_id} set to use {target_file}")

        # 4. Execute Workflow
        output_files = get_images(ws, workflow, client_id, job)
        
        # 5. Encode Results
        result_images = {}
        for filename in output_files:
            file_path = os.path.join(OUTPUT_DIR, filename)
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    result_images[filename] = base64.b64encode(f.read()).decode('utf-8')
            else:
                print(f"⚠️ Expected output file missing: {filename}")

        return {"status": "success", "images": result_images}

    except Exception as e:
        print(f"❌ Handler Error: {str(e)}")
        return {"status": "error", "message": str(e)}
        
    finally:
        ws.close()
        if debug_mode:
            print("⚠️ DEBUG MODE: Files preserved in /dev/shm (input/output)")
        else:
            clear_directory(INPUT_DIR)
            clear_directory(OUTPUT_DIR)

if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
