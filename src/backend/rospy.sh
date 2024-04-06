# miniforge setup for Python env management
wget -O Miniforge3.sh "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
bash Miniforge3.sh -b -p "${HOME}/conda"
source "${HOME}/conda/etc/profile.d/conda.sh"
# Also adding support for mamba
source "${HOME}/conda/etc/profile.d/mamba.sh"
conda activate

# Robostack setup
conda install -y mamba -c conda-forge
mamba create -n ros_env -y
mamba activate ros_env
# configure channels for new environment
conda config --env --add channels conda-forge
conda config --env --add channels robostack-staging
conda config --env --remove channels defaults
# install ros-noetic-desktop
mamba install -y ros-noetic-desktop
mamba deactivate
mamba activate ros_env
