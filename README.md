# ROS Annotator

ROS Annotator is a standalone web application designed to facilitate the analysis of ROSBag data, with a special focus on Human-Robot Interaction (HRI) captured in various formats, including video streams, 3D point clouds, and custom HRI messages. The application will support loading multiple ROSBags, connecting to an auto-transcription tool for processing audio data, and providing a synchronised, interactive dashboard for data visualisation. Users will be able to manually annotate interactions with custom scales, annotating states (e.g., "child looking at the robot") and events (e.g., "child entering input on the table").

## Team Information

| Name | Email | Position |
|------|-------|----------|
| Bowen Fan | bffa@student.unimelb.edu.au | Product Manager |
| Tianqi Wang | tww2@student.unimelb.edu.au | Scrum Master |
| Guanqin Wang | guanqinw@student.unimelb.edu.au | DevOps Manager|
| Yujie Zheng | yujiezheng@student.unimelb.edu.au | Backend Developer |
| Yuchen Song | yuchsong2@student.unimelb.edu.au | Frontend Developer |
| Yucheng Peng | yucpeng1@student.unimelb.edu.au | ROS Analyst |
| Abhishek Tummalapalli | atummalapall@student.unimelb.edu.au | TBD |

## Repository Structure

```
├── docs/          # Documentation files
└── src/           # Source code for the project
    ├── backend/   # Backend application code
    └── frontend/  # Frontend application code
```

## Setup Guide

### Prerequisites

To get started, you'll need to have the following tools installed on your system:

- **Node.js 20.11.1**
- **npm 10.5.0**
- **Python 3.12.2**

### Frontend

1. Navigate to the Frontend Directory: <code>cd src/frontend</code>
2. Install Node.js dependencies: <code>npm install</code>
3. Run the frontend server with <code>npm start</code>

### Backend

1. Navigate to the Backend Directory: <code>cd src/backend</code>
2. Install dependencies: <code>pip install -r requirements.txt</code>
3. Run the backend server with <code>python manage.py runserver</code>