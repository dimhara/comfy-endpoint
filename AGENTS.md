# AGENTS.md - Developer Guide

This document explains the architecture, security model, and critical synchronization logic of the `dimhara-comfy-endpoint` project for future LLM agents and developers.

## 1. Project Goal
To provide a production-grade, security-hardened container for running ComfyUI on RunPod Serverless, optimized for high-speed ephemeral execution and data privacy.

**Current Status:** Production Ready (v2.0).
**Key Pillars:** Data Encryption, RAM-disk I/O, Race-Condition Protection.

## 2. Security & Privacy Model

### "Single Token" Encryption (AES-256)
*   **Mechanism:** Uses the `cryptography.fernet` (AES-256-CBC + HMAC) standard.
*   **Logic:** The client bundles the modified workflow JSON and all input images into a single dictionary, then encrypts that entire object into a string called `encrypted_input`.
*   **Privacy:** This hides the prompt, the number of images, filenames, and the node structure from RunPod logs and unauthorized observers.
*   **Key Management:** Both client and server must have the `ENCRYPTION_KEY` environment variable set.
*   **Debug Bypass:** Using the `--debug` flag on the client disables encryption, sending plaintext data to allow for troubleshooting via RunPod's system logs.

### Network & Access
*   **Localhost Binding:** ComfyUI is configured to listen on `127.0.0.1:8188`. It is never exposed to the public internet.
*   **SSH Tunneling:** Remote access to the GUI for workflow design is achieved via SSH tunneling (`ssh -L 8188:127.0.0.1:8188`).
*   **Secure Wipe:** The `rp_handler.py` overwrites files in `/dev/shm` (RAM disk) with zero-bytes before deletion to prevent data remnants in shared memory.

## 3. The "Serverless Gap" (Critical Fixes)

Executing ComfyUI in a high-speed ephemeral environment requires specific synchronization logic implemented in `rp_handler.py`:

### Input Race Condition (Solved)
*   **Issue:** Python and OS buffering on RAM disks can result in ComfyUI reading a 0-byte file if the API is triggered immediately after a file write.
*   **Solution:** Forced `f.flush()` followed by `os.fsync(f.fileno())` after saving every input image.

### History API Race Condition (Solved)
*   **Issue:** ComfyUI often fires the "Execution Finished" WebSocket message before the metadata is fully written to its SQLite history database.
*   **Solution:** A retry loop (5 attempts with 200ms backoff) in `get_images()` to ensure the History entry is populated before the handler returns.

### Output File Handle Race (Solved)
*   **Issue:** Attempting to read output images immediately after the "Finished" signal can occasionally clash with ComfyUI's file-close operation.
*   **Solution:** A 100ms `time.sleep()` buffer before encoding output files to Base64.

## 4. Components

### `rp_handler.py` (The Core)
*   **Logic:** Decrypts the `encrypted_input`, wipes directories, writes files to `/dev/shm`, triggers ComfyUI, monitors progress, and retrieves result metadata.

### `client.py` (The Smart Client)
*   **Multi-Image Support:** Automatically maps multiple images (`--img 1.png 2.png`) to `LoadImage` nodes based on their numerical ID order.
*   **Injection Logic:** Detects node types (`CLIPTextEncode` vs `TextEncodeQwen...`) and injects the `--prompt` into the correct internal field.
*   **Resumption:** Includes a `--resume-id` flag to reconnect to a job if the local client crashes while polling.

### `utils.py` (Model Manager)
*   **Host Cache First:** Prioritizes symbolic linking from `/runpod-volume/huggingface-cache`.
*   **Renaming:** Supports renaming models during download (critical for GGUF/mmproj files).

## 5. Environment Variables
| Variable | Description | Required |
| :--- | :--- | :--- |
| `ENCRYPTION_KEY` | AES-256 Fernet key. | Yes (unless debug) |
| `MODELS` | Comma-delimited list of HF models to sync. | Yes |
| `PUBLIC_KEY` | SSH Public Key for tunnel access. | Optional |
| `HF_TOKEN` | Hugging Face token for private repos. | Optional |

## 6. Maintenance
*   **Update ComfyUI:** Rebuild the Base Image; the Docker cache will pull the latest `master` branch.
*   **New Nodes:** Add `git clone` commands to the Builder stage of the `Dockerfile`.
*   **Hardware Compatibility:** For modern FP8/Flux models, avoid the `--fast` flag in `start.sh` if deploying to older GPU architectures (Pre-Ampere) to prevent math corruption (NaNs).
