import requests
import time
import base64
import os
import json
import argparse

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# Replace these with your RunPod credentials
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
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="Secure ComfyUI RunPod Client")
    parser.add_argument("--workflow", default="workflow_api.json", help="API Workflow JSON file")
    parser.add_argument("--img", help="Path to input image (e.g. photo.jpg)")
    parser.add_argument("--poll_interval", type=int, default=2, help="Seconds between status checks")
    
    args = parser.parse_args()

    # 1. Load Workflow JSON
    if not os.path.exists(args.workflow):
        print(f"❌ Error: Workflow file '{args.workflow}' not found.")
        return

    with open(args.workflow, "r") as f:
        workflow_data = json.load(f)

    # 2. Prepare Payload
    payload = {
        "input": {
            "workflow": workflow_data,
            "images": {}
        }
    }

    # 3. Handle Input Image & Smart Injection
    if args.img:
        b64_data = encode_image(args.img)
        if b64_data:
            # We use the actual filename for the remote system
            remote_filename = os.path.basename(args.img)
            payload["input"]["images"][remote_filename] = b64_data
            
            # Find and Update the LoadImage node in the JSON
            found_node = False
            for node_id, node_data in workflow_data.items():
                if node_data.get("class_type") == "LoadImage":
                    print(f"🎯 Smart Injection: Updating Node {node_id} to use '{remote_filename}'")
                    node_data["inputs"]["image"] = remote_filename
                    found_node = True
            
            if not found_node:
                print("⚠️  Warning: Image provided but no 'LoadImage' node found in JSON.")

    # 4. Submit Job (Async /run)
    print(f"🚀 Submitting job to RunPod Endpoint {ENDPOINT_ID}...")
    try:
        run_resp = requests.post(f"{BASE_URL}/run", json=payload, headers=HEADERS)
        run_resp.raise_for_status()
        job_id = run_resp.json().get("id")
        
        if not job_id:
            print(f"❌ Error: No Job ID returned. Response: {run_resp.json()}")
            return
            
        print(f"🆔 Job ID: {job_id}")
    except Exception as e:
        print(f"❌ Submission Failed: {e}")
        return

    # 5. Polling Loop
    print("⏳ Polling for results and progress...")
    last_status = None
    
    while True:
        try:
            status_resp = requests.get(f"{BASE_URL}/status/{job_id}", headers=HEADERS)
            status_resp.raise_for_status()
            data = status_resp.json()
            
            status = data.get("status")

            # Update status line if it changes
            if status != last_status:
                print(f"\nStatus: {status}", end="", flush=True)
                last_status = status
            
            # Display Progress (from runpod.serverless.progress_update in handler)
            if "progress" in data:
                print(f" | Progress: {data['progress']}", end="", flush=True)

            if status == "COMPLETED":
                print(f"\n\n✅ Job Completed Successfully!")
                output = data.get("output", {})
                
                if output.get("status") == "success":
                    images = output.get("images", {})
                    if not images:
                        print("ℹ️  Job succeeded but no output images were returned.")
                    
                    for filename, b64_data in images.items():
                        # Save result with 'out_' prefix
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
                # IN_QUEUE or IN_PROGRESS
                print(".", end="", flush=True)
                time.sleep(args.poll_interval)

        except KeyboardInterrupt:
            print(f"\n\n🛑 Polling interrupted. The job is STILL RUNNING on the server.")
            print(f"   To check later, use Job ID: {job_id}")
            break
        except Exception as e:
            print(f"\n⚠️  Connection Error: {e}. Retrying...")
            time.sleep(5)

if __name__ == "__main__":
    main()
