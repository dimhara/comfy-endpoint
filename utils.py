import os
import shutil
from huggingface_hub import hf_hub_download

# RunPod Serverless Cache Directory (Standard location)
RUNPOD_CACHE_DIR = "/runpod-volume/huggingface-cache/hub"

def get_model_map():
    """
    Parses the MODELS environment variable.
    Format: RepoID:RemoteFile:TargetDir[:LocalRename]
    """
    models_env = os.environ.get("MODELS", "")
    if not models_env:
        return []
    
    model_list = []
    entries = [e.strip() for e in models_env.split(",") if e.strip()]
    
    for entry in entries:
        parts = entry.split(":")
        if len(parts) < 3:
            continue
            
        repo_id = parts[0].strip()
        filename = parts[1].strip()
        target_dir = parts[2].strip()
        local_name = parts[3].strip() if len(parts) > 3 else None
        
        model_list.append({
            "repo_id": repo_id,
            "filename": filename,
            "target_dir": target_dir,
            "local_name": local_name
        })
            
    return model_list

def prepare_models():
    base_path = os.getcwd() 
    model_list = get_model_map()
    
    # Check if we have a persistent network volume
    # If yes, we use it for caching and symlink to save space.
    # If no, we download and MOVE to save space.
    use_network_cache = os.path.exists(RUNPOD_CACHE_DIR)
    
    if not model_list:
        return

    print(f"--- 📦 Processing {len(model_list)} models ---")
    if use_network_cache:
        print(f"   ✅ Network Volume Detected: {RUNPOD_CACHE_DIR}")
    else:
        print(f"   ⚠️  No Network Volume. Using ephemeral storage (Download -> Move).")

    for m in model_list:
        repo_id = m["repo_id"]
        filename = m["filename"]
        
        # Resolve destination
        if m["target_dir"].startswith("/"):
            dest_dir = m["target_dir"]
        else:
            dest_dir = os.path.join(base_path, m["target_dir"])
            
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)

        final_name = m["local_name"] if m["local_name"] else os.path.basename(filename)
        dest_path = os.path.join(dest_dir, final_name)

        if os.path.exists(dest_path):
            print(f"✅ Exists: {dest_path}")
            continue

        print(f"⬇️  Resolving: {repo_id}/{filename}")
        
        try:
            # 1. DOWNLOAD
            # If using network cache, force that dir. Otherwise use default (~/.cache).
            cache_target = RUNPOD_CACHE_DIR if use_network_cache else None
            
            cached_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                cache_dir=cache_target
            )
            
            # 2. LINK or MOVE
            if use_network_cache:
                # Symlink: Data stays on volume, ComfyUI sees a file. Zero container space used.
                print(f"   🔗 Symlinking: {cached_path} -> {dest_path}")
                if os.path.exists(dest_path) or os.path.islink(dest_path):
                    os.remove(dest_path)
                os.symlink(cached_path, dest_path)
            else:
                # Move: Take file out of cache and put it in ComfyUI. 
                # Clears the cache space and puts data where needed.
                print(f"   🚚 Moving: {cached_path} -> {dest_path}")
                
                # We use copy+remove because moving across filesystems (if /root/.cache is a volume) can fail,
                # but standard move usually handles it. 
                # However, since cached_path in HF might be a symlink to a blob, we must be careful.
                # hf_hub_download returns the actual file path (resolving symlinks) usually.
                
                # Use shutil.move which handles copy-then-delete if needed.
                shutil.move(cached_path, dest_path)
            
        except Exception as e:
            print(f"❌ Error processing {repo_id}/{filename}: {e}")

if __name__ == "__main__":
    prepare_models()
