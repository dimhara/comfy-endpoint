# AGENTS.md - Developer Guide

This document explains the architecture and design philosophy of the `comfy-secure` project for future LLM agents and developers.

## 1. Project Goal
To create a high-performance, security-focused container for running ComfyUI on Serverless GPU providers (specifically RunPod).

**Current Status:** Infrastructure Phase (Base Image + SSH + Model Management).
**Next Phase:** Implementation of `rp_handler.py` for Serverless API wrapping.

## 2. Directory Structure & Logic

### `utils.py` (The Model Manager)
*   **Purpose:** Handles downloading models from Hugging Face or linking them from the RunPod Host Cache (`/runpod-volume/huggingface-cache`).
*   **Syntax:** It parses the `MODELS` environment variable using a colon-delimited format:
    `RepoID : RemoteFilename : TargetDir [ : LocalRename ]`
*   **Renaming Logic:**
    *   If `LocalRename` is provided, the file is saved/linked as that specific name.
    *   This is critical for files like `mmproj-BF16.gguf` which ComfyUI-GGUF expects to be named `*-mmproj-*.gguf`.
    *   It also handles flattening nested HF paths (e.g., `split_files/vae/vae.safetensors` -> `models/vae/vae.safetensors`).

### `Dockerfile` (Multi-Stage)
*   **Builder Stage:** Uses `nvidia/cuda-devel` to install system build tools. Uses `uv` to create a Python virtual environment (`.venv`) and install ComfyUI + Nodes.
*   **Runtime Stage:** Uses `nvidia/cuda-runtime`. Copies **only** the `/ComfyUI` folder and the `.venv` from the builder. This reduces image size and removes compiler attack surfaces.

### `Dockerfile.baked`
*   **Purpose:** Extends the base image to include heavy model files directly in the Docker image layer.
*   **Use Case:** Faster cold-starts on RunPod (no download time), at the cost of larger image storage.
*   **Mechanism:** Sets the `MODELS` ARG and runs `utils.py` during the build process.

### `start.sh`
*   **Role:** The Container Entrypoint.
*   **Flow:**
    1.  Sets up OpenSSH server (generates keys if missing).
    2.  Runs `utils.py` to ensure models are present (downloading if not "baked").
    3.  Activates the `uv` virtual environment.
    4.  Launches ComfyUI in listen mode.

## 3. Environment Variables
| Variable | Description |
| :--- | :--- |
| `MODELS` | Comma-separated list of models to download/link. |
| `PUBLIC_KEY` | SSH Public Key for authorized access. |
| `HF_TOKEN` | (Optional) Hugging Face token for private repos. |
| `HF_HUB_ENABLE_HF_TRANSFER` | Enabled by default for fast downloads. |

---

## 4. Maintenance Notes
*   **ComfyUI Updates:** To update ComfyUI, rebuild the Base Image (Docker cache will break at the `git clone` step if the repo has changed).
*   **New Nodes:** Add `git clone` commands in the Builder stage of the `Dockerfile`.

## 5. Security & Networking
*   **Localhost Binding:** ComfyUI is configured in `start.sh` to listen on `127.0.0.1`. 
*   **Tunneling:** To access the Web UI, an SSH tunnel must be established (`ssh -L 8188:127.0.0.1:8188`). 
*   **Rationale:** This prevents unauthorized access via RunPod's public-facing proxy/IPs.
