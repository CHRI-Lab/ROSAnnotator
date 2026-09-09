# syntax=docker/dockerfile:1

# The large ROS/CUDA/PyTorch dependency layers are built separately and
# published only when the base dependencies change.
ARG BACKEND_BASE_IMAGE=ghcr.io/kihara001/hri-sim-group6-backend-base:gpu-v1@sha256:5e41f697df35b67f74f48c1fab6974df0388bd1fc6c9102e5515220ef4c80261
FROM ${BACKEND_BASE_IMAGE}

WORKDIR /app

# Keep Python dependencies aligned with this revision even when the published
# GPU base image was built from an older requirements.txt. This layer is cached
# until requirements.txt changes.
COPY --link requirements.txt /tmp/requirements.txt
RUN /root/conda/envs/ros_env/bin/python -m pip install \
        --no-cache-dir -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

# COPY --link keeps the application layer independent from the large base
# layers, allowing BuildKit to rebase without downloading the full base image.
COPY --link manage.py ./
COPY --link ros_annotator/ ./ros_annotator/
COPY --link rosbag_processing/ ./rosbag_processing/
COPY --link public/ ./public/

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
