#!/bin/bash

# Define color variables
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print headers
print_header() {
    local separator=$(printf '%*s' 50 '' | tr ' ' '=')
    echo -e "${BLUE}${separator}"
    echo -e "$1"
    echo -e "${separator}${NC}"
}
# Function to print progress messages
print_progress() {
    echo -e "${YELLOW}$1${NC}"
}
# Function to print success messages
print_success() {
    echo -e "${GREEN}$1${NC}"
}
# Function to print error messages
print_error() {
    echo -e "${RED}$1${NC}"
}
# Error handling
error_occurred() {
    print_error "An error occurred during the installation process. Please check the messages above for more information."
    exit 1
}

# Trap any error
trap 'error_occurred' ERR

# Miniforge setup for Python env management
print_header "Miniforge Setup for Python Environment Management"
print_progress "Downloading Miniforge3..."
wget -O Miniforge3.sh "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
print_success "Download complete."

print_progress "Installing Miniforge3..."
bash Miniforge3.sh -b -p "${HOME}/conda"
source "${HOME}/conda/etc/profile.d/conda.sh"
print_success "Installation complete."

print_progress "Adding support for Mamba..."
source "${HOME}/conda/etc/profile.d/mamba.sh"
print_success "Mamba support added."

# Activate the base env with mamba
mamba activate
print_success "Mamba activated."

# Robostack setup
print_header "Robostack Setup"
print_progress "Creating ROS environment with Mamba..."
mamba create -n ros_env python=3.9 -y
mamba activate ros_env
print_success "ROS environment created and activated."

print_progress "Configuring channels for the new environment..."
conda config --env --add channels conda-forge
conda config --env --add channels robostack-staging
conda config --env --remove channels defaults || true
print_success "Channels configured."

print_header "Installing ros-noetic-desktop..."
mamba install -y ros-noetic-desktop
mamba install -y compilers cmake pkg-config make ninja colcon-common-extensions catkin_tools rosdep
print_success "ros-noetic-desktop installed."

print_header "Installing additional packages..."
conda install -n ros_env -y ipykernel --update-deps --force-reinstall
rm -rf /root/conda/envs/ros_env/lib/python3.11/site-packages/cv2*
rm -rf /root/conda/envs/ros_env/lib/python3.11/site-packages/opencv*
pip3 install opencv-python-headless
print_success "Additional packages installed."

mamba deactivate
mamba activate ros_env
print_success "ROS environment reactivated by Mamba."

echo -e "${GREEN}Setup completed successfully.${NC}"
