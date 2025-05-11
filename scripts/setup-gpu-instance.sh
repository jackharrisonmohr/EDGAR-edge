#!/bin/bash
set -e

#Configured to run on vast.ai instance with Ubuntu 22.04, torch, and NVIDIA drivers pre-installed.

# Constants
# CUDA_DEB="cuda-repo-ubuntu2204-12-1-local_12.1.1-530.30.02-1_amd64.deb"
# CUDA_URL="https://developer.download.nvidia.com/compute/cuda/12.1.1/local_installers/$CUDA_DEB"

echo ">>> Updating system and installing base dependencies..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y git wget unzip tmux build-essential python3-pip python3-venv curl

echo ">>> Installing Python 3.12..."
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev



echo ">>> Installing Poetry..."
curl -sSL https://install.python-poetry.org | python3 -
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# echo ">>> Installing NVIDIA drivers and CUDA..."
# wget $CUDA_URL
# sudo dpkg -i $CUDA_DEB
# sudo cp /var/cuda-repo-ubuntu2204-12-1-local/cuda-*.key /usr/share/keyrings/
# sudo apt update
# sudo apt install -y cuda

echo ">>> Verifying NVIDIA GPU visibility..."
nvidia-smi || { echo "❌ ERROR: GPU not detected. Check instance type."; exit 1; }

# echo ">>> Installing PyTorch with CUDA support..."
# pip install --upgrade pip
# pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

echo ">>> Installing aws cli..."
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

echo ">>> Cloning EDGAR-Edge repo..."
# If you already uploaded it via SCP, skip this. Otherwise:
git clone https://github.com/jackharrisonmohr/EDGAR-Edge
cd EDGAR-Edge
echo ">>> Configuring Poetry to use Python 3.12..."
poetry env use $(which python3.12)

echo ">>> Installing project dependencies via Poetry..."
poetry install

echo "✅ Setup complete. Ready to fine-tune."

echo "💡 Next step: Upload your edgar_labels.parquet file to this instance."
echo "Then run: poetry run python src/research/finetune_roberta_script.py"
