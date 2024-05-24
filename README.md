# ROS Annotator
## Project Overview
The ROSAnnotator project aims to develop a standalone web application specifically designed to enhance the analysis of Robot Operating System Bag (ROSBag) data, with a particular emphasis on Human-Robot Interaction (HRI). ROSBags are a crucial element in robotics research, serving as a standard format for logging and replaying messages within the ROS ecosystem. These logs can include a wide variety of data types, such as video streams, 3D point clouds, and custom messages tailored for HRI studies. The application is envisioned to be a versatile tool for researchers, enabling the loading of multiple ROSBags, integration with auto-transcription tools for audio data processing, and the provision of a synchronized, interactive dashboard for intuitive data visualization.

## Project Background
Human-Robot Interaction (HRI) is a growing field of study that explores how humans interact with robots in various contexts, from industrial applications to personal assistance and beyond. The analysis of HRI data is complex, involving multiple modalities such as visual data, audio communications, and sensor data from the robot. The ROS ecosystem provides a flexible framework for robot development and research, but the analysis of ROSBag data, especially from HRI experiments, requires specialized tools. Existing tools like Elan offer some capabilities for annotation and analysis but may not fully meet the unique needs of HRI research, such as handling specific ROS data types or synchronizing multiple data streams.

## Project Goal
*  The primary goal of ROSAnnotator is to fill this gap by providing a comprehensive tool that facilitates the detailed analysis of HRI experiments. The project focuses on several key objectives:

*  Data Handling Capabilities: To build robust support for reading and parsing the diverse data types contained in ROSBags, ensuring researchers can access and analyze all relevant data components of their HRI experiments.

*  Synchronised Interactive Dashboard: To develop an intuitive, user-friendly interface that displays various data streams in a synchronized manner, allowing researchers to interact with and analyze data more effectively.

*  Annotation Features: To enable detailed annotations of HRI interactions, including custom scales for states (e.g., "child looking at the robot") and events (e.g., "child entering input on the table"), thereby enhancing the depth and specificity of analysis.

*  Integration and Automation: Although given less priority initially, integrating with auto-transcription tools for audio data and exploring automatic annotation methods based on audio transcripts are also envisioned to streamline the annotation process and make the tool more versatile.

## Project Timeline

[Overall project management link with Trello board](https://comp90082-2024-na-koala.atlassian.net/wiki/spaces/comp900822/pages/6062124/Sprint+Management+with+Trello+Board)


[Project Confluence Home Page](https://comp90082-2024-na-koala.atlassian.net/wiki/spaces/comp900822/overview?homepageId=589914)

### Sprint 1 (3.11-3.22)
[Link](https://comp90082-2024-na-koala.atlassian.net/wiki/spaces/comp900822/pages/3932161/Sprint+1) to documentation

### Sprint 2 (3.23-5.2)
[Link](https://comp90082-2024-na-koala.atlassian.net/wiki/spaces/comp900822/pages/7143431/Sprint+2) to documentation
### Sprint 3 (5.3-5.24)
[Link](https://comp90082-2024-na-koala.atlassian.net/wiki/spaces/comp900822/pages/7471122/Sprint+3) to documentation
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

#### Sprint 2
https://drive.google.com/file/d/19A8k8uDG5NgB5xpRQiOwexR_nYtFT-9I/view?pli=1


#### Sprint 3
https://drive.google.com/file/d/1TVW8IRGzAULBHdEeJwETAcFMruCib3e5/view?usp=sharing 