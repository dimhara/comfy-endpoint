import os
import shutil
import glob
from huggingface_hub import hf_hub_download

# Standard RunPod Host Cache Path
RUNPOD_CACHE_DIR = "/runpod-volume/huggingface-cache/hub"

def get_model_map():
    models_env = os.environ.get("MODELS", "")
    if not models_env:
        return []
    model_list = []
    entries = [e.strip() for e in models_env.split(",") if e.strip()]
    for entry in entries:
        parts = entry.split(":")
        if len(parts) < 3: continue
        model_list.append({
            "repo_id": parts[0].strip(),
            "filename": parts[1].strip(),
            "target_dir": parts[2].strip(),
            "local_name": parts[3].strip() if len(parts) > 3 else None
        })
    return model_list

def find_in_runpod_cache(repo_id, filename):
    """
    Checks if the file exists in the RunPod Network Volume.
    RunPod structure: models--user--repo/snapshots/{hash}/{filename}
    """
    if not os.path.exists(RUNPOD_CACHE_DIR):
        return None

    safe_repo = f"models--{repo_id.replace('/', '--')}"
    repo_path = os.path.join(RUNPOD_CACHE_DIR, safe_repo, "snapshots")
    
    if not os.path.exists(repo_path):
        return None

    # Search through all snapshot hashes for the file
    for snapshot in os.listdir(repo_path):
        full_path = os.path.join(repo_path, snapshot, filename)
        if os.path.exists(full_path):
            # Resolve to the actual blob path to avoid broken relative links
            return os.path.realpath(full_path)
    return None

def prepare_models():
    model_list = get_model_map()
    if not model_list:
        return

    print(f"--- 📦 Processing {len(model_list)} models ---")

    for m in model_list:
        repo_id = m["repo_id"]
        filename = m["filename"]
        
        # 1. Resolve Final Destination
        dest_dir = m["target_dir"] if m["target_dir"].startswith("/") else os.path.join(os.getcwd(), m["target_dir"])
        os.makedirs(dest_dir, exist_ok=True)
        
        final_basename = m["local_name"] if m["local_name"] else os.path.basename(filename)
        final_dest_path = os.path.join(dest_dir, final_basename)

        if os.path.exists(final_dest_path):
            print(f"✅ Already exists: {final_dest_path}")
            continue

        # 2. Check RunPod Host Cache First (Instant Start)
        cached_physical_path = find_in_runpod_cache(repo_id, filename)
        
        if cached_physical_path:
            print(f"🚀 Found in RunPod Cache! Linking: {cached_physical_path}")
            # We use an absolute symlink. ComfyUI follows it, and it uses 0GB of disk.
            os.symlink(cached_physical_path, final_dest_path)
            print(f"   ✅ Instant link created at: {final_dest_path}")
            continue

        # 3. Fallback to v1.4.0 Download API
        print(f"⬇️  Not in cache. Downloading {repo_id}/{filename}...")
        try:
            downloaded_path = hf_hub_download(
                repo_id=repo_id, 
                filename=filename, 
                local_dir=dest_dir
            )

            # 4. Flatten/Rename if necessary
            if downloaded_path != final_dest_path:
                print(f"   🚚 Flattening/Renaming: {downloaded_path} -> {final_dest_path}")
                shutil.move(downloaded_path, final_dest_path)
                
                # Cleanup empty subdirs
                parent_dir = os.path.dirname(downloaded_path)
                while parent_dir != dest_dir:
                    if not os.listdir(parent_dir):
                        os.rmdir(parent_dir)
                        parent_dir = os.path.dirname(parent_dir)
                    else:
                        break
            
            print(f"   ✅ Successfully placed at: {final_dest_path}")

        except Exception as e:
            print(f"❌ Error processing {filename}: {e}")

if __name__ == "__main__":
    prepare_models()
