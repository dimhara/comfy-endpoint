import requests
import time
import base64
import os
import json
import argparse
import random
from cryptography.fernet import Fernet

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# Replace these with your actual RunPod credentials
ENDPOINT_ID = "YOUR_ENDPOINT_ID"
API_KEY = "YOUR_API_KEY"

# Pull key from environment variable
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")

BASE_URL = f"https://api.runpod.ai/v2/{ENDPOINT_ID}"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# ==============================================================================
# HELPERS
# ==============================================================================
def encode_image(path):
    """Converts a local image file to a base64 string."""
    if not os.path.exists(path):
        print(f"❌ Error: Image file '{path}' not found.")
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

def encrypt_payload(data_dict):
    """Encrypts a dictionary into a single Fernet token."""
    if not ENCRYPTION_KEY:
        print("❌ Error: ENCRYPTION_KEY environment variable not set.")
        exit(1)
    try:
        f = Fernet(ENCRYPTION_KEY.encode())
        json_bytes = json.dumps(data_dict).encode()
        return f.encrypt(json_bytes).decode()
    except Exception as e:
        print(f"❌ Encryption Error: {e}")
        exit(1)

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="Secure ComfyUI RunPod Client")
    parser.add_argument("--workflow", default="workflow_api.json", help="API Workflow JSON file")
    parser.add_argument("--img", nargs='+', help="Input image(s). Mapped to LoadImage nodes by ID order.")
    parser.add_argument("--prompt", help="Custom text prompt")
    parser.add_argument("--poll_interval", type=int, default=2, help="Seconds between status checks")
    parser.add_argument("--debug", action="store_true", help="Disable encryption for troubleshooting")
    
    args = parser.parse_args()

    # 1. Load Workflow JSON
    if not os.path.exists(args.workflow):
        print(f"❌ Error: Workflow file '{args.workflow}' not found.")
        return

    with open(args.workflow, "r") as f:
        workflow_data = json.load(f)

    # 2. Smart Injection (Plaintext Processing)
    images_to_upload = {}
    
    # A. Handle Multiple Images
    if args.img:
        # Identify all LoadImage nodes and sort by numerical ID
        load_image_nodes = []
        for node_id, node_data in workflow_data.items():
            if node_data.get("class_type") == "LoadImage":
                load_image_nodes.append((int(node_id), node_data))
        
        load_image_nodes.sort(key=lambda x: x[0])
        
        for i, img_path in enumerate(args.img):
            if i >= len(load_image_nodes):
                print(f"⚠️ Warning: More images provided than LoadImage nodes. Skipping {img_path}")
                continue
            
            b64_data = encode_image(img_path)
            if b64_data:
                remote_name = os.path.basename(img_path)
                images_to_upload[remote_name] = b64_data
                
                target_node_id = load_image_nodes[i][0]
                target_node_data = load_image_nodes[i][1]
                target_node_data["inputs"]["image"] = remote_name
                print(f"🎯 Image Injection: '{img_path}' -> Node {target_node_id}")

    # B. Handle Prompt and Seed Injection
    for node_id, node_data in workflow_data.items():
        class_type = node_data.get("class_type")

        # Inject Prompt
        if args.prompt:
            if class_type == "CLIPTextEncode":
                node_data["inputs"]["text"] = args.prompt
                print(f"✍️  Prompt Injection (CLIP): Node {node_id}")
            elif class_type == "TextEncodeQwenImageEditPlus" and str(node_id) == "24":
                node_data["inputs"]["prompt"] = args.prompt
                print(f"✍️  Prompt Injection (Qwen): Node {node_id}")

        # Randomize Seed
        if "seed" in node_data.get("inputs", {}):
            new_seed = random.randint(1, 10**15)
            node_data["inputs"]["seed"] = new_seed
            print(f"🎲 Seed Randomized: Node {node_id}")

    # 3. Construct Payload (Encryption Layer)
    is_encrypted = not args.debug
    
    # Sensitive data bundle
    inner_payload = {
        "workflow": workflow_data,
        "images": images_to_upload
    }

    if is_encrypted:
        print("🔒 Encrypting payload...")
        encrypted_token = encrypt_payload(inner_payload)
        payload = {
            "input": {
                "encrypted_input": encrypted_token,
                "is_encrypted": True,
                "debug": False
            }
        }
    else:
        print("⚠️  DEBUG MODE: Sending plaintext data.")
        payload = {
            "input": {
                "workflow": workflow_data,
                "images": images_to_upload,
                "is_encrypted": False,
                "debug": True
            }
        }

    # 4. Submit Job
    print(f"🚀 Submitting job to RunPod Endpoint {ENDPOINT_ID}...")
    try:
        run_resp = requests.post(f"{BASE_URL}/run", json=payload, headers=HEADERS)
        run_resp.raise_for_status()
        job_id = run_resp.json().get("id")
        print(f"🆔 Job ID: {job_id}")
    except Exception as e:
        print(f"❌ Submission Failed: {e}")
        return

    # 5. Polling Loop
    print("⏳ Polling for results...")
    last_status = None
    
    while True:
        try:
            status_resp = requests.get(f"{BASE_URL}/status/{job_id}", headers=HEADERS)
            status_resp.raise_for_status()
            data = status_resp.json()
            status = data.get("status")

            if status != last_status:
                print(f"\nStatus: {status}", end="", flush=True)
                last_status = status
            
            if "progress" in data:
                print(f" | Progress: {data['progress']}", end="", flush=True)

            if status == "COMPLETED":
                print(f"\n\n✅ Job Completed Successfully!")
                output = data.get("output", {})
                
                if output.get("status") == "success":
                    images = output.get("images", {})
                    if not images:
                        print("ℹ️  No output images returned.")
                    
                    for filename, b64_data in images.items():
                        out_filename = f"out_{filename}"
                        with open(out_filename, "wb") as f:
                            f.write(base64.b64decode(b64_data))
                        print(f"💾 Saved: {out_filename}")
                else:
                    print(f"❌ Worker Error: {output.get('message')}")
                break

            elif status in ["FAILED", "CANCELLED"]:
                print(f"\n❌ Job {status}!")
                print(f"   Error: {data.get('error')}")
                break
            else:
                print(".", end="", flush=True)
                time.sleep(args.poll_interval)

        except KeyboardInterrupt:
            print(f"\n\n🛑 Polling interrupted. Job ID: {job_id}")
            break
        except Exception as e:
            time.sleep(5)

if __name__ == "__main__":
    main()
