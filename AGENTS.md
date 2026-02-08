# AGENTS.md - Developer Guide

This document explains the architecture, design philosophy, and critical operational details of the `dimhara-comfy-endpoint` project.

## 1. Project Goal
To provide a production-grade, serverless-ready container for running ComfyUI on RunPod, specifically optimized for high-speed ephemeral execution.

**Current Status:** Production Ready.
**Key Features:** Secure RAM-disk I/O, Race-Condition protections, Multi-Image injection, and Smart Prompting.

## 2. Critical Architecture Notes (The "Serverless Gap")

Moving from a persistent Pod to Serverless introduces specific challenges regarding filesystem timing and API synchronization.

### The "RAM Disk Race" (Solved)
*   **Problem:** On Serverless, `/ComfyUI/input` is a symlink to `/dev/shm` (RAM). When `rp_handler.py` writes a file and immediately triggers the ComfyUI API, Python's internal buffer or the OS filesystem buffer may not flush to "disk" fast enough. ComfyUI reads the file as 0 bytes, causing "Noise" output or silent failures.
*   **Solution:** The handler now forces `f.flush()` and `os.fsync(f.fileno())` immediately after writing input images.

### The "History API Race" (Solved)
*   **Problem:** ComfyUI sends the "Execution Finished" WebSocket message *milliseconds* before it writes the metadata to its internal History database. Querying `/history/{prompt_id}` immediately often returns 404 or empty data.
*   **Solution:** `rp_handler.py` implements a retry loop (5 retries with backoff) to wait for the database write to complete.

## 3. Directory Structure & Logic

### `rp_handler.py` (The Serverless Bridge)
*   **Input:** Accepts Base64 images and a JSON workflow.
*   **Processing:**
    1.  Wipes input/output directories (Secure Delete).
    2.  Decodes images to `/ComfyUI/input` with **forced fsync**.
    3.  Injects the workflow via WebSocket.
    4.  Polls for progress.
    5.  Retries the History API to capture filenames.
    6.  Encodes output images to Base64.
*   **Debug Mode:** If `debug: true` is passed in the payload, files are *not* deleted after execution, allowing SSH inspection.

### `client.py` (The Smart Client)
*   **Multi-Image Support:** Accepts multiple images (`--img 1.png 2.png`). It maps them to `LoadImage` nodes in the workflow based on Node ID order (lowest ID first).
*   **Smart Injection:**
    *   **Images:** Replaces filenames in `LoadImage` nodes and uploads the Base64 data.
    *   **Prompts:** Detects if a node is `CLIPTextEncode` (Standard) or `TextEncodeQwenImageEditPlus` (Custom) and injects text into the correct field.
    *   **Seeds:** Automatically randomizes inputs named `seed` to ensure variety.
*   **Polling:** Handles the async nature of RunPod's `/run` and `/status` endpoints.

### `utils.py` (The Model Manager)
*   **Purpose:** Handles downloading models from Hugging Face or linking them from the RunPod Host Cache (`/runpod-volume/huggingface-cache`).
*   **Logic:** Prioritizes Host Cache (Symlinks) > Hugging Face Download. This ensures 0GB disk usage if the host has the model.

## 4. Operational Guide

### Deploying Updates
1.  **Code Changes:** Commit changes to `rp_handler.py` or `start.sh`.
2.  **Build:** The GitHub Action `build-base.yml` will automatically build and push to GHCR.
3.  **RunPod:** Restart the generic Pod or update the Serverless Endpoint Image URL (forcing a fresh pull).

### Debugging "Noise" or "Empty Output"
If the endpoint returns success but the image is random noise:
1.  **Check I/O:** It is likely the Input Race Condition. Ensure `os.fsync` is active in the handler.
2.  **Glass Box Test:**
    *   Deploy as a standard GPU Pod.
    *   SSH Tunnel: `ssh -L 8188:127.0.0.1:8188 root@<IP>`.
    *   Run `client.py` against `localhost` (requires modifying client URL) OR use the Web UI to verify the workflow integrity.

### Debugging "Job Succeeded but No Output"
If the client says "Job succeeded" but saves no files:
1.  **Check History:** It is the History API Race Condition. Ensure the retry loop in `rp_handler.py` is active.
2.  **Debug Mode:** Run `python client.py ... --debug`. SSH into the serverless worker (if active) and check `/ComfyUI/output` to see if files actually exist.

## 5. Environment Variables
| Variable | Description |
| :--- | :--- |
| `MODELS` | Comma-separated list of models to download/link (RepoID:Filename:Target). |
| `PUBLIC_KEY` | SSH Public Key for authorized access. |
| `HF_TOKEN` | (Optional) Hugging Face token. |

## 6. Security
*   **Localhost Binding:** ComfyUI listens on `127.0.0.1`.
*   **Secure Wipe:** Files are overwritten with zeros before deletion to prevent RAM scraping.
*   **SSH:** Only accessible via Key-based authentication.

