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

# Activate conda
conda activate
print_success "Conda activated."

# Robostack setup
print_header "Robostack Setup"
print_progress "Installing Mamba from conda-forge..."
conda install -y mamba -c conda-forge
print_success "Mamba installed."

print_progress "Creating ROS environment..."
mamba create -n ros_env -y
mamba activate ros_env
print_success "ROS environment created and activated."

print_progress "Configuring channels for the new environment..."
conda config --env --add channels conda-forge
conda config --env --add channels robostack-staging
conda config --env --remove channels defaults || true
print_success "Channels configured."

print_header "Installing ros-noetic-desktop..."
mamba install -y ros-noetic-desktop
print_success "ros-noetic-desktop installed."

mamba deactivate
mamba activate ros_env
print_success "ROS environment reactivated."

echo -e "${GREEN}Setup completed successfully.${NC}"
