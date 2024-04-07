#!/bin/bash

source "${HOME}/conda/etc/profile.d/conda.sh"
conda activate ros_env
pip3 install --no-cache-dir -r requirements.txt
