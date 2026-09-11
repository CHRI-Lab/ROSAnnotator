# syntax=docker/dockerfile:1

# The large ROS/CUDA/PyTorch dependency layers are built separately and
# published only when the base dependencies change.
ARG BACKEND_BASE_IMAGE=ghcr.io/kihara001/hri-sim-group6-backend-base:gpu-v2@sha256:d3f12b214ef323eddc24f86a3e2c65148572c0ea45b47e453f14d23cda750c10
FROM ${BACKEND_BASE_IMAGE}

# Video extraction, audio decoding through pydub, and video/audio muxing invoke
# the ffmpeg command-line tools at runtime. Install them in the application
# image so local and tester builds do not depend on the host machine.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Keep the existing published base image compatible with the versions tested
# with ROSAnnotator. These pins should also be included in the next base image.
RUN /root/conda/envs/ros_env/bin/python -m pip install \
    --no-cache-dir \
    "huggingface_hub==0.24.6" \
    "speechbrain==1.0.0" \
    "torch==2.5.1" \
    "torchvision==0.20.1" \
    "torchaudio==2.5.1"

WORKDIR /app

# COPY --link keeps the application layer independent from the large base
# layers, allowing BuildKit to rebase without downloading the full base image.
COPY --link manage.py ./
COPY --link ros_annotator/ ./ros_annotator/
COPY --link rosbag_processing/ ./rosbag_processing/
COPY --link public/ ./public/

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
