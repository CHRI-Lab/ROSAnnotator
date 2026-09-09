# syntax=docker/dockerfile:1

# The large ROS/CUDA/PyTorch dependency layers are built separately and
# published only when the base dependencies change.
ARG BACKEND_BASE_IMAGE=ghcr.io/kihara001/hri-sim-group6-backend-base:gpu-v2@sha256:d3f12b214ef323eddc24f86a3e2c65148572c0ea45b47e453f14d23cda750c10
FROM ${BACKEND_BASE_IMAGE}

WORKDIR /app

# COPY --link keeps the application layer independent from the large base
# layers, allowing BuildKit to rebase without downloading the full base image.
COPY --link manage.py ./
COPY --link ros_annotator/ ./ros_annotator/
COPY --link rosbag_processing/ ./rosbag_processing/
COPY --link public/ ./public/

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
