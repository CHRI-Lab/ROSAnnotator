# Backend Setup and Development Guide

This document provides a comprehensive guide for running (or setting up) the development environment and workflow for the backend of our project. It includes instructions for preparing all the `ROS` dependencies, starting the backend `Django` server, developing within the environment, and placing `rosbag` files.

> - The backend is running on Python version **3.9** & Django version **4.2**
> - The `rosbag` analysis is done by using **ROS1 Noetic** and related Python packages provided by [RoboStack](https://robostack.github.io/index.html). Please refer to the [ROS Environment](#ros-environment) section for more details.
> - Base image for Docker: `ubuntu:jammy` (Ubuntu 22.04)

## Prerequisites

#### Docker Installation

- Before you begin, ensure that you have Docker installed on your machine. If not, download and install Docker from [Docker's official site](https://www.docker.com/get-started).
- Verify that the **Docker daemon** is running by executing `docker info` in your terminal. This should return information about the Docker client and server. If not, please start the Docker daemon.

## Starting the Backend Server

To start the backend server, follow these steps:

1. **Navigate to the Backend Directory**

   Change to the backend folder by running:

   ```bash
   cd src/backend
   ```

2. **Start the Server**

   Use Docker Compose to start the backend services:

   ```bash
   docker-compose up
   ```

   This command will build the image using `Dockerfile` from ground up and start all the required backend services as defined in the `docker-compose.yml` file. It also installs all the `ROS` dependencies.

   > _Note: The image size is about 4.84 GB, so it may take a while for the first time to download and build the image. The speed depends on your computational resources and internet connection._

   Use the below command to check the image and the status of running container:

   ```bash
   # you should see a image with the name 'backend:ros-annotator'
   docker image ls
   # you should see a running container with the name 'ros-annotator'
   docker ps
   ```

3. **Access the Backend Server**

   Once the server is up and running, you can access the backend server at `http://localhost:8000/`. You should see the Django REST framework interface.

   > _Note: The backend server is running in development mode, and the backend code base has been map to the container through Docker volume, so it will automatically reload whenever you make changes to the code._

   Visit `http://localhost:5678/` for debugging purposes.

## Development Setup Guide & Workflow

To develop on the backend, proceed with the following steps (or see the gif below for a visual guide):

1. **VSCode Extensions**: Ensure you have the Dev Container extension installed in your VSCode. The Dev Container extension allows you to develop inside a Docker container.
2. **Attach to the Running Container**: In VSCode, use the Dev Container extension to attach to the running Docker container. This can typically be done through the command palette (Ctrl+Shift+P or Cmd+Shift+P) and selecting "Attach to Running Container."
3. **Install Necessary Extensions in Dev Container**: Within the dev container environment in VSCode, install the Python (and Jupyter extensions if you are going to run Jupyter Notebook) to facilitate development. (_Note: This only need to be done once when you attach the container for the first time._)

## Using Rosbag Datas

To work with `rosbag` files:

- **Data Placement**: Place your rosbag data into the `src/backend/rosbag-data` folder. This location is set up to be accessible within the backend environment using docker volume.

## ROS Environment

In this project, the ROS environment is uniquely integrated with our backend. Instead of starting from a pre-built `ros` Docker image available on DockerHub, we build our image from a basic Ubuntu system. This approach is chosen to enhance the integrability with Python and our backend components.

#### Why RoboStack?

We utilize [RoboStack](https://robostack.github.io/index.html) to set up the ROS environment from scratch on a Linux image. RoboStack provides a comprehensive suite of libraries and CLIs that facilitate interaction between `ROS` and Python APIs, optimizing our entire development workflow. Following the requirements of RoboStack, we used Miniforge as the tool to manage Conda and our virtual environment (venv).

## Related Links

(Please check out the following repos)

#### **Rosbag Analysis:**

- https://github.com/bowenfan-unimelb/rosbag-analysis by @bowenfan-unimelb
- https://github.com/ypen1127/project-research by @ypen1127
