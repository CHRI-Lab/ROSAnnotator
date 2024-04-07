# ubuntu 20.04
FROM ubuntu:focal

# Install dependencies
RUN apt-get update \
    && apt-get install -y wget \
    && apt-get install -y ffmpeg libsm6 libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Copy files for env setup and set the permission
COPY env_config/ /env_config/
RUN chmod -R +x /env_config/

# Run the script to configure Python and ROS env
RUN /env_config/forge-ros.sh

# Setup the backend of ros-annotator
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements.txt
RUN /env_config/backend.sh

# Arugment completion for every new terminal
RUN cat /env_config/bashrc >> ${HOME}/.bashrc

# Start the backend & ROS server
ENTRYPOINT [ "/env_config/entrypoint.sh" ]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
