import os
import json
import base64
import sys

# Import the handler function from your script
try:
    from rp_handler import handler
except ImportError:
    print("❌ Error: rp_handler.py not found in the current directory.")
    sys.exit(1)

# CONFIGURATION FOR LOCAL TEST
MOCK_INPUT_IMAGE = "input_test.png"  # Path to a local image you want to test with
MOCK_WORKFLOW_JSON = "workflow_api.json" # Path to your ComfyUI API JSON
SAVE_OUTPUT_TO = "test_results"

def encode_image(path):
    """Helper to convert local file to base64 string"""
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

def main():
    print("--- 🧪 Starting Local Handler Test ---")
    
    # 1. Load your ComfyUI API Workflow
    if not os.path.exists(MOCK_WORKFLOW_JSON):
        print(f"❌ Error: {MOCK_WORKFLOW_JSON} not found.")
        print("   Please export your workflow from ComfyUI using 'Save (API Format)'.")
        return

    with open(MOCK_WORKFLOW_JSON, "r") as f:
        workflow = json.load(f)

    # 2. Construct the Mock Job Input
    # This matches the structure RunPod will send
    job_input = {
        "workflow": workflow,
        "images": {}
    }

    # 3. Attach an input image if it exists locally
    # Note: Ensure your workflow LoadImage node is looking for "input_image.png"
    b64_image = encode_image(MOCK_INPUT_IMAGE)
    if b64_image:
        print(f"📷 Encoding input image: {MOCK_INPUT_IMAGE}")
        job_input["images"]["input_image.png"] = b64_image
    else:
        print("ℹ️  No input image found. Running text-to-image or skipping image-to-image logic.")

    # 4. Wrap in RunPod's job structure
    mock_job = {
        "id": "test-local-uuid-12345",
        "input": job_input
    }

    # 5. Execute the Handler
    print("\n🚀 Invoking handler logic (ensure ComfyUI is running on localhost:8188)...")
    result = handler(mock_job)

    # 6. Process the Results
    print(f"\n🏁 Handler Status: {result.get('status')}")
    
    if result.get("status") == "success":
        images = result.get("images", {})
        print(f"✅ Success! Received {len(images)} output images.")
        
        if not os.path.exists(SAVE_OUTPUT_TO):
            os.makedirs(SAVE_OUTPUT_TO)

        for filename, b64_data in images.items():
            out_path = os.path.join(SAVE_OUTPUT_TO, f"local_test_{filename}")
            with open(out_path, "wb") as f:
                f.write(base64.b64decode(b64_data))
            print(f"💾 Saved result to: {out_path}")
    else:
        print(f"❌ Error Message: {result.get('message')}")

if __name__ == "__main__":
    main()
