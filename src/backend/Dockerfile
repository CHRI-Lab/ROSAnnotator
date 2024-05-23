# ubuntu 20.04
FROM ubuntu:focal

# Install dependencies
RUN apt-get update \
    && apt-get install -y wget dos2unix python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Copy files for env setup and set the permission
COPY env_config/ /env_config/
RUN chmod -R +x /env_config/
RUN dos2unix /env_config/forge-ros.sh
RUN dos2unix /env_config/entrypoint.sh
RUN dos2unix /env_config/backend.sh

RUN ls -l /env_config/
RUN cat /env_config/entrypoint.sh

# Install ROS
RUN bash /env_config/forge-ros.sh

# Install python dependencies
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements.txt

# Install python dependencies
RUN pip3 install -r requirements.txt

# Set the environment variables
RUN /env_config/backend.sh

# Add the bashrc file
RUN cat /env_config/bashrc >> ${HOME}/.bashrc

# Start the backend & ROS server
ENTRYPOINT ["/bin/bash", "/env_config/entrypoint.sh"]
CMD ["python3", "manage.py", "runserver", "0.0.0.0:8000"]
