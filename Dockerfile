# ==========================================
# STAGE 1: BUILDER
# ==========================================
FROM nvidia/cuda:13.0.2-runtime-ubuntu22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

# 1. Install System Dependencies
RUN apt-get update && apt-get install -y \
    git curl python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# 2. Install UV (The modern 2026 standard for Python)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /
RUN git clone --depth 1 https://github.com/Comfy-Org/ComfyUI

WORKDIR /ComfyUI
RUN uv venv
ENV VIRTUAL_ENV=/ComfyUI/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# 3. Install PyTorch 2.10 for CUDA 13.0
# Using the cu130 index for the 2026 runtime
RUN uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130

# 4. Install ComfyUI Core
RUN uv pip install --no-cache-dir -r requirements.txt

# 5. Custom Nodes & Handler Tools
WORKDIR /ComfyUI/custom_nodes
RUN git clone --depth 1 https://github.com/city96/ComfyUI-GGUF && \
    cd ComfyUI-GGUF && \
    uv pip install --no-cache-dir -r requirements.txt

RUN uv pip install --no-cache-dir huggingface_hub[hf_transfer] runpod requests websocket-client cryptography

# 6. Clean Builder Layer
RUN rm -rf /ComfyUI/.git && \
    find /ComfyUI/custom_nodes -name ".git" -type d -exec rm -rf {} + && \
    rm -rf /root/.cache/uv

# ==========================================
# STAGE 2: RUNTIME
# ==========================================
FROM nvidia/cuda:13.0.2-runtime-ubuntu22.04 AS final

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    python3 python3-pip openssh-server \
    libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /
COPY --from=builder /ComfyUI /ComfyUI

ENV VIRTUAL_ENV=/ComfyUI/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV HF_HUB_ENABLE_HF_TRANSFER=1

COPY utils.py /ComfyUI/utils.py
COPY rp_handler.py /ComfyUI/rp_handler.py
COPY start.sh /start.sh
RUN chmod +x /start.sh

WORKDIR /ComfyUI
EXPOSE 22
CMD ["/start.sh"]
