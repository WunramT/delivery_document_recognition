# docval: local test/evaluation environment. CPU by default, CUDA via build arg.
FROM python:3.11-slim-bookworm

ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
ARG WITH_REFERENCE=1

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DOCVAL_DATA=/data DOCVAL_MODELS=/models PYTHONPATH=/workspace/src

# OpenCV (libgl1, libglib2.0-0), PDF rendering (poppler-utils), fonts for the smoke dataset,
# C compiler: Triton JIT-compiles a helper on the GPU path (Hungarian matcher)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libgomp1 poppler-utils fonts-dejavu-core make git gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp/req
COPY requirements.txt requirements-reference.txt ./
# torch/torchvision first from the selected PyTorch index (cpu or cu126); the pins
# in requirements.txt are then already satisfied, everything else comes from PyPI
RUN pip install --index-url ${TORCH_INDEX} \
        "torch==$(sed -n 's/^torch==//p' requirements.txt)" \
        "torchvision==$(sed -n 's/^torchvision==//p' requirements.txt)" \
    && pip install -r requirements.txt \
    && if [ "${WITH_REFERENCE}" = "1" ]; then \
         pip install -r requirements-reference.txt \
         && pip install --force-reinstall --no-deps opencv-contrib-python==4.10.0.84; \
       fi

WORKDIR /workspace
