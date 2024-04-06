FROM ubuntu:jammy

# Install dependencies
RUN apt-get update \
    && apt-get install -y wget \
    && rm -rf /var/lib/apt/lists/*

# Copy files for env setup and set the permission
COPY env_config/ /env_config/
RUN chmod -R +x /env_config/

# Run the script to configure Python and ROS env
RUN /env_config/forge-ros.sh

# Run the script to setup the backend of ros-annotator
# RUN /env_config/backend.sh

# Arugment completion for every new terminal
RUN cat /env_config/bashrc >> ${HOME}/.bashrc


#
# ENTRYPOINT [ "/env_config/entrypoint.sh" ]
CMD ["bash"]
