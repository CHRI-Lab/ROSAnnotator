FROM ubuntu:jammy

# Install dependencies
RUN apt-get update \
    && apt-get install -y wget \
    && rm -rf /var/lib/apt/lists/*

# Run the script to configure Python and ROS env
COPY env_config/ /env_config/
RUN /env_config/forge-ros.sh

# Run the script to setup the backend
# RUN /env_config/backend.sh


# 
CMD ["/env_config/activate.sh"]