import os
import shutil
from huggingface_hub import hf_hub_download

# RunPod Serverless Cache Directory (Standard location)
RUNPOD_CACHE_DIR = "/runpod-volume/huggingface-cache/hub"

def get_model_map():
    """
    Parses the MODELS environment variable.
    Format: RepoID:RemoteFile:TargetDir[:LocalRename]
    Example: unsloth/Qwen:mmproj.gguf:models/text_encoders:qwen-mmproj.gguf
    """
    models_env = os.environ.get("MODELS", "")
    if not models_env:
        print("ℹ️  No MODELS environment variable set.")
        return []
    
    model_list = []
    # Split by comma, ignore empty strings
    entries = [e.strip() for e in models_env.split(",") if e.strip()]
    
    for entry in entries:
        parts = entry.split(":")
        if len(parts) < 3:
            print(f"⚠️  Skipping invalid entry: {entry}")
            continue
            
        repo_id = parts[0].strip()
        filename = parts[1].strip()
        target_dir = parts[2].strip()
        
        # Optional 4th argument for renaming (e.g. for mmproj or flattening VAE)
        local_name = parts[3].strip() if len(parts) > 3 else None
        
        model_list.append({
            "repo_id": repo_id,
            "filename": filename,
            "target_dir": target_dir,
            "local_name": local_name
        })
            
    return model_list

def prepare_models():
    """
    Downloads or copies models based on the MODELS env var.
    """
    # Assuming this runs from /ComfyUI
    base_path = os.getcwd() 
    
    model_list = get_model_map()
    if not model_list:
        return

    print(f"--- 📦 Processing {len(model_list)} models ---")

    for m in model_list:
        repo_id = m["repo_id"]
        filename = m["filename"]
        
        # Resolve destination directory
        if m["target_dir"].startswith("/"):
            dest_dir = m["target_dir"]
        else:
            dest_dir = os.path.join(base_path, m["target_dir"])
            
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)

        # Determine final file name (handle renaming)
        final_name = m["local_name"] if m["local_name"] else os.path.basename(filename)
        dest_path = os.path.join(dest_dir, final_name)

        if os.path.exists(dest_path):
            print(f"✅ Already exists: {dest_path}")
            continue

        print(f"⬇️  Resolving: {repo_id}/{filename}")
        
        try:
            # hf_hub_download automatically checks RUNPOD_CACHE_DIR if HF_HOME is set there,
            # or uses the default ~/.cache/huggingface/hub.
            cached_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
            )
            
            # Move/Copy from HF cache to the ComfyUI folder structure
            # shutil.copy is used to ensure the file remains in the cache for future pods
            # but is also available in the specific ComfyUI path.
            shutil.copy(cached_path, dest_path)
            print(f"   💾 Saved to: {dest_path}")
            
        except Exception as e:
            print(f"❌ Error processing {repo_id}/{filename}: {e}")

if __name__ == "__main__":
    prepare_models()
