# ROS Annotator
## Project Overview
The ROSAnnotator project aims to develop a standalone web application specifically designed to enhance the analysis of Robot Operating System Bag (ROSBag) data, with a particular emphasis on Human-Robot Interaction (HRI). ROSBags are a crucial element in robotics research, serving as a standard format for logging and replaying messages within the ROS ecosystem. These logs can include a wide variety of data types, such as video streams, 3D point clouds, and custom messages tailored for HRI studies. The application is envisioned to be a versatile tool for researchers, enabling the loading of multiple ROSBags, the provision of a synchronized, interactive dashboard for intuitive data visualization and Connected with Chatgpt API which can automatically annotate by interaction with GPT.

## Project Background
Human-Robot Interaction (HRI) is a growing field of study that explores how humans interact with robots in various contexts, from industrial applications to personal assistance and beyond. The analysis of HRI data is complex, involving multiple modalities such as visual data, audio communications, and sensor data from the robot. The ROS ecosystem provides a flexible framework for robot development and research, but the analysis of ROSBag data, especially from HRI experiments, requires specialized tools. Existing tools like Elan offer some capabilities for annotation and analysis but may not fully meet the unique needs of HRI research, such as handling specific ROS data types or synchronizing multiple data streams.


## Project Structure

The ROS Annotator project integrates ROS (Robot Operating System) with Django for processing and annotating ROS bag files. The project also includes a React-based frontend for interacting with the annotations and managing data.



The project is organized into the following main directories:

### Root Directory

```.github/```: GitHub configuration files, including workflow actions for continuous integration.

```data-samples/```: Sample data and related documentation for testing and demonstration.

```src/```: The main source code for the project, divided into backend and frontend sections.


### Backend

Located in ```src/backend/```, this directory contains the Django backend code for handling ROS bag files and serving data to the frontend.

```urls.py```: URL routing for the Django project.

```asgi.py & wsgi.py```: ASGI and WSGI configurations for deployment.

```rosbag_processing/```: Application for processing and handling ROS bag files.

```data_utils.py & file_utils.py```: Utility functions for data and file operations.

```views.py```: API endpoints for interacting with ROS bag data.

```Dockerfile```: Dockerfile for building the backend container.

```docker-compose.yml```: Docker Compose configuration for the backend services.

```requirements.txt```: List of Python dependencies required by the backend.

### Frontend

Located in ```src/frontend/```, this directory contains the React frontend code for the user interface of the ROS Annotator.

```components/```: Reusable React components such as AnnotationTable, Timeline, and Transcript.

```pages/```: Page components for different routes, including Annotator, Landing, and Main.



## Repository Structure

The ROS Annotator project integrates ROS (Robot Operating System) with Django for processing and annotating ROS bag files. The project also includes a React-based frontend for interacting with the annotations and managing data.


```
├── .github/         # GitHub configuration and workflows
├── data-samples/    # Sample data for testing
├── src/             # Source code for the project
│   ├── backend/    # Backend (Django) application code
│   │   ├── asgi.py # ASGI config
│   │   ├── wsgi.py # WSGI config
│   │   ├── urls.py # URL routing
│   │   ├── rosbag_processing/  # ROSBag processing code
│   │   │   ├── views.py        # API endpoints related to ROSBag
│   │   │   └── data_utils.py   # Data utilities related to ROSBag
│   │   ├── Dockerfile          # Dockerfile for backend
│   │   └── requirements.txt    # Python dependencies
│   └── frontend/   # Frontend (React) application code
│       ├── components/  # Reusable React components
│       └── pages/       # Page components for different routes
├── docker-compse.yml # Docker Compose config
└── datas/            # Will be created after building the Docker image
    ├── rosbag-data/ # Place your ROSBag data here
    ├── booklist/    # Place your predefined codebook here
    ├── annotation/  # Retrieve your annotation output here
    └── processed/   # Store all processed data of a ROSBag with timestamps

```

## Usage Guide

1. **Prerequisites - Docker Installation**

   - Before you begin, ensure that you have Docker installed on your machine. If not, download and install Docker from [Docker's official site](https://www.docker.com/get-started).
   - Verify that the **Docker daemon** is running by executing `docker info` in your terminal. This should return information about the Docker client and server. If not, please start the Docker daemon.

2. **Starting the Server**

   Run the following commands in the root directory of the project:

   ```bash
   docker-compose up --build
   ```

   > _Note: The total image size is about 5 GB, so it may take a while for the first time to download and build the image. The speed depends on your computational resources and internet connection._

4. **Enviroment**

    Application require OpenAI API Key (ChatGPT) and Hugging Face Access Token. Before running it in docker, please create a .env file in root path of **backend** and place two variables **OPENAI_API_KEY** and  **HUGGINGFACE_AUTH_TOKEN** inside manually.

5. **Access the Application**

   Both the frontend and the backend is hosted in a Docker container locally. Once the server is up and running, you can access the [web app](http://localhost:5173/) at `http://localhost:5173/`.

## Setup & Development Guide

### Frontend

See [README.md](https://github.com/COMP90082-2024-SM1/ros-annotator/tree/main/src/frontend#readme) at <code>src/frontend</code>

### Backend

See [README.md](https://github.com/COMP90082-2024-SM1/ros-annotator/blob/main/src/backend/readme.md) at <code>src/backend</code>

## Product Demo Video

#### Sprint 2 Please open with unimelb email account
https://drive.google.com/file/d/19A8k8uDG5NgB5xpRQiOwexR_nYtFT-9I/view?pli=1


#### Sprint 3 Please open with unimelb email account
https://drive.google.com/file/d/1TVW8IRGzAULBHdEeJwETAcFMruCib3e5/view?usp=sharing 
