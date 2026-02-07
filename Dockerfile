# ==========================================
# STAGE 1: BUILDER
# ==========================================
FROM nvidia/cuda:12.4.1-devel-ubuntu22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

# 1. Install System Dependencies
RUN apt-get update && apt-get install -y \
    git curl python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# 2. Install UV (Extremely fast Python package installer)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /

# 3. Clone ComfyUI (Depth 1 for smaller layer size)
RUN git clone --depth 1 https://github.com/Comfy-Org/ComfyUI

WORKDIR /ComfyUI

# 4. Create Virtual Environment via UV
RUN uv venv
ENV VIRTUAL_ENV=/ComfyUI/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# 5. Install ComfyUI Core Requirements
RUN uv pip install --no-cache-dir -r requirements.txt

# 6. Install Custom Nodes
WORKDIR /ComfyUI/custom_nodes

# --- NODE: ComfyUI-GGUF ---
RUN git clone --depth 1 https://github.com/city96/ComfyUI-GGUF
WORKDIR /ComfyUI/custom_nodes/ComfyUI-GGUF
RUN uv pip install --no-cache-dir -r requirements.txt

# 7. Install Hugging Face Tools (required for utils.py)
RUN uv pip install --no-cache-dir huggingface_hub[hf_transfer]

# ==========================================
# STAGE 2: RUNTIME
# ==========================================
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS final

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# 1. Install Runtime Dependencies
# openssh-server: For SSH tunneling/debugging
# libgl1/libglib2.0-0: Required for OpenCV/Image processing in many nodes
RUN apt-get update && apt-get install -y \
    python3 python3-pip openssh-server \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /

# 2. Copy the entire ComfyUI directory (including .venv) from Builder
COPY --from=builder /ComfyUI /ComfyUI

# 3. Environment Configuration
ENV VIRTUAL_ENV=/ComfyUI/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV HF_HUB_ENABLE_HF_TRANSFER=1

# 4. Copy Infrastructure Scripts
COPY utils.py /ComfyUI/utils.py
COPY start.sh /start.sh
RUN chmod +x /start.sh

WORKDIR /ComfyUI

EXPOSE 22

# 6. Set Entrypoint
CMD ["/start.sh"]

