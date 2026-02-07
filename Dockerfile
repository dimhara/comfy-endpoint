# ==========================================
# STAGE 1: BUILDER
# ==========================================
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

# 1. Install System Dependencies
# git: for cloning
# curl: for downloading uv
# python3-venv: required for uv venv
RUN apt-get update && apt-get install -y \
    git curl python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# 2. Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /

# 3. Clone ComfyUI (Depth 1)
RUN git clone --depth 1 https://github.com/Comfy-Org/ComfyUI

WORKDIR /ComfyUI

# 4. Create Virtual Environment
RUN uv venv
ENV VIRTUAL_ENV=/ComfyUI/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130

# 5. Install Core Requirements
RUN uv pip install --no-cache-dir -r requirements.txt

# 6. Install Custom Nodes
WORKDIR /ComfyUI/custom_nodes

# --- NODE: ComfyUI-GGUF ---
RUN git clone --depth 1 https://github.com/city96/ComfyUI-GGUF
WORKDIR /ComfyUI/custom_nodes/ComfyUI-GGUF
RUN uv pip install --no-cache-dir -r requirements.txt

# 7. Install Hugging Face Tools
RUN uv pip install --no-cache-dir huggingface_hub[hf_transfer] runpod requests websocket-client

# 8. Cleanup builder
# Remove git history and UV cache to keep the layer small
RUN rm -rf /ComfyUI/.git && \
    find /ComfyUI/custom_nodes -name ".git" -type d -exec rm -rf {} + && \
    rm -rf /root/.cache/uv

# ==========================================
# STAGE 2: RUNTIME
# ==========================================
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS final

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# 1. Runtime System Deps
# openssh-server: For SSH
# libgl1/libglib2.0-0: For OpenCV
RUN apt-get update && apt-get install -y \
    python3 python3-pip openssh-server \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /

# 2. Copy the cleaned ComfyUI directory
COPY --from=builder /ComfyUI /ComfyUI

# 3. Environment Setup
ENV VIRTUAL_ENV=/ComfyUI/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV HF_HUB_ENABLE_HF_TRANSFER=1

# 4. Copy Scripts
COPY utils.py /ComfyUI/utils.py
COPY rp_handler.py /ComfyUI/rp_handler.py
COPY start.sh /start.sh
RUN chmod +x /start.sh

WORKDIR /ComfyUI

# 5. Ports (SSH only since Comfy binds to localhost)
EXPOSE 22

CMD ["/start.sh"]