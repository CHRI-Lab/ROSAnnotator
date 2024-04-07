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
print_header "Reintializing PATH Variables"
print_progress "Adding Forge and Conda to PATH..."
source "${HOME}/conda/etc/profile.d/conda.sh"
source "${HOME}/conda/etc/profile.d/mamba.sh"
print_success "Commands added to PATH."

# Activate the correct virtual environment
print_header "Activating ROS & Python Environment"
print_progress "Activating ros_env from mamba..."
conda activate ros_env
print_success "ros_env reactivated."

echo -e "${GREEN}Setup completed successfully.${NC}"

# Execute the command
exec $@
