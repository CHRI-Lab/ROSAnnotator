# ROS Annotator
## Project Overview
The ROSAnnotator project aims to develop a standalone web application specifically designed to enhance the analysis of Robot Operating System Bag (ROSBag) data, with a particular emphasis on Human-Robot Interaction (HRI). ROSBags are a crucial element in robotics research, serving as a standard format for logging and replaying messages within the ROS ecosystem. These logs can include a wide variety of data types, such as video streams, 3D point clouds, and custom messages tailored for HRI studies. The application is envisioned to be a versatile tool for researchers, enabling the loading of multiple ROSBags, the provision of a synchronized, interactive dashboard for intuitive data visualization and Connected with Chatgpt API which can automatically annotate by interaction with GPT.

## Project Background
Human-Robot Interaction (HRI) is a growing field of study that explores how humans interact with robots in various contexts, from industrial applications to personal assistance and beyond. The analysis of HRI data is complex, involving multiple modalities such as visual data, audio communications, and sensor data from the robot. The ROS ecosystem provides a flexible framework for robot development and research, but the analysis of ROSBag data, especially from HRI experiments, requires specialized tools. Existing tools like Elan offer some capabilities for annotation and analysis but may not fully meet the unique needs of HRI research, such as handling specific ROS data types or synchronizing multiple data streams.

## Project Sturcture


## Repository Structure

```
├── docs/          # Documentation files
├── data-samples/  # Data samples
└── src/           # Source code for the project
    ├── backend/   # Backend application code
    └── frontend/  # Frontend application code
├── tests/         # Test files
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

3. **Data Placement**

   After running the above command, Docker will automatically create the below folders in the root directory of the project:

   ```
   └── datas/
       ├── rosbag-data/   # place your rosbag data here
       ├── booklist/   # place your predefined booklist here
       └── annotation/  # retrieve your annotation output here
       └── processed/  # store all processed data of a rosbag with timestamps
   ```

   To use the desired data or files, place them into the corresponding folders. This location is set up to be accessible within the backend environment using attached docker volumes.

4. **Access the Application**

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
