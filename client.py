import requests
import time
import base64
import os
import json
import argparse
import random

# ==============================================================================
# CONFIGURATION
# ==============================================================================
ENDPOINT_ID = "YOUR_ENDPOINT_ID"
API_KEY = "YOUR_API_KEY"

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

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="Secure ComfyUI RunPod Client")
    parser.add_argument("--workflow", default="workflow_api.json", help="API Workflow JSON file")
    
    # [UPDATED] nargs='+' allows one OR more images
    parser.add_argument("--img", nargs='+', help="Path(s) to input image(s). First image goes to first LoadImage node, etc.")
    
    parser.add_argument("--prompt", help="Custom text prompt for the image edit")
    parser.add_argument("--poll_interval", type=int, default=1, help="Seconds between status checks")
    parser.add_argument("--debug", action="store_true", help="Leave files on server for SSH inspection")
    
    args = parser.parse_args()

    # 1. Load Workflow JSON
    if not os.path.exists(args.workflow):
        print(f"❌ Error: Workflow file '{args.workflow}' not found.")
        return

    with open(args.workflow, "r") as f:
        workflow_data = json.load(f)

    # 2. Prepare Payload Base
    payload = {
        "input": {
            "workflow": workflow_data,
            "images": {},
            "debug": args.debug
        }
    }

    # 3. Smart Injection Logic
    
    # A. Handle Multiple Images
    if args.img:
        # 1. Identify all LoadImage nodes
        load_image_nodes = []
        for node_id, node_data in workflow_data.items():
            if node_data.get("class_type") == "LoadImage":
                load_image_nodes.append((int(node_id), node_data))
        
        # 2. Sort by ID (e.g., Node 16 comes before Node 28)
        load_image_nodes.sort(key=lambda x: x[0])
        
        # 3. Map input files to nodes
        for i, img_path in enumerate(args.img):
            if i >= len(load_image_nodes):
                print(f"⚠️ Warning: More images provided ({len(args.img)}) than 'LoadImage' nodes found ({len(load_image_nodes)}). Ignoring '{img_path}'.")
                continue
            
            b64_data = encode_image(img_path)
            if b64_data:
                remote_filename = os.path.basename(img_path)
                
                # Add to payload
                payload["input"]["images"][remote_filename] = b64_data
                
                # Update specific node
                target_node_id = load_image_nodes[i][0]
                target_node_data = load_image_nodes[i][1]
                target_node_data["inputs"]["image"] = remote_filename
                
                print(f"🎯 Image Injection: Mapped '{img_path}' -> Node {target_node_id} (LoadImage)")

    # B. Handle Prompts & Seeds
    for node_id, node_data in workflow_data.items():
        class_type = node_data.get("class_type")

        # Prompt Injection
        if args.prompt:
            if class_type == "CLIPTextEncode":
                node_data["inputs"]["text"] = args.prompt
                print(f"✍️  Prompt Injection (CLIP): Node {node_id} updated.")
            elif class_type == "TextEncodeQwenImageEditPlus" and str(node_id) == "24":
                node_data["inputs"]["prompt"] = args.prompt
                print(f"✍️  Prompt Injection (Qwen): Node {node_id} updated.")

        # Seed Randomization
        if "seed" in node_data.get("inputs", {}):
            new_seed = random.randint(1, 10**15)
            node_data["inputs"]["seed"] = new_seed
            print(f"🎲 Randomized Seed: Node {node_id} -> {new_seed}")

    # 4. Submit Job (Async /run)
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
                         print("ℹ️  Job succeeded but no output images returned (Check Handler/History API).")
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
            time.sleep(2)

if __name__ == "__main__":
    main()
