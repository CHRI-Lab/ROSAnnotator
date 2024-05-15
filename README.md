# ROS Annotator

ROS Annotator is a standalone web application designed to facilitate the analysis of ROSBag data, with a special focus on Human-Robot Interaction (HRI) captured in various formats, including video streams, 3D point clouds, and custom HRI messages. The application will support loading multiple ROSBags, connecting to an auto-transcription tool for processing audio data, and providing a synchronised, interactive dashboard for data visualisation. Users will be able to manually annotate interactions with custom scales, annotating states (e.g., "child looking at the robot") and events (e.g., "child entering input on the table").

## Team Information

| Name                  | Email                               | Position           |
| --------------------- | ----------------------------------- | ------------------ |
| Bowen Fan             | bffa@student.unimelb.edu.au         | Product Manager    |
| Tianqi Wang           | tww2@student.unimelb.edu.au         | Scrum Master       |
| Guanqin Wang          | guanqinw@student.unimelb.edu.au     | DevOps Manager     |
| Yujie Zheng           | yujiezheng@student.unimelb.edu.au   | Backend Developer  |
| Yuchen Song           | yuchsong2@student.unimelb.edu.au    | Frontend Developer |
| Yucheng Peng          | yucpeng1@student.unimelb.edu.au     | ROS Analyst        |
| Abhishek Tummalapalli | atummalapall@student.unimelb.edu.au | ROS Analyst        |

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
   ```

   To use the desired data or files, place them into the corresponding folders. This location is set up to be accessible within the backend environment using attached docker volumes.

4. **Access the Application**

   Both the frontend and the backend is hosted in a Docker container locally. Once the server is up and running, you can access the [web app](http://localhost:5173/) at `http://localhost:5173/`.

## Setup & Development Guide

### Frontend

See [README.md](https://github.com/COMP90082-2024-SM1/ros-annotator/tree/main/src/frontend#readme) at <code>src/frontend</code>

### Backend

See [README.md](https://github.com/COMP90082-2024-SM1/ros-annotator/blob/main/src/backend/readme.md) at <code>src/backend</code>

## Product Demo (Sprint 2)

https://drive.google.com/file/d/19A8k8uDG5NgB5xpRQiOwexR_nYtFT-9I/view?pli=1
