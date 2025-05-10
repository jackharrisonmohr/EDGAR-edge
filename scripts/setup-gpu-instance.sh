#!/bin/bash
set -e

# Constants
CUDA_DEB="cuda-repo-ubuntu2204-12-1-local_12.1.1-530.30.02-1_amd64.deb"
CUDA_URL="https://developer.download.nvidia.com/compute/cuda/12.1.1/local_installers/$CUDA_DEB"

echo ">>> Updating system and installing base dependencies..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y git wget unzip tmux build-essential python3-pip python3-venv curl

echo ">>> Installing Poetry..."
curl -sSL https://install.python-poetry.org | python3 -
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

echo ">>> Installing NVIDIA drivers and CUDA..."
wget $CUDA_URL
sudo dpkg -i $CUDA_DEB
sudo cp /var/cuda-repo-ubuntu2204-12-1-local/cuda-*.key /usr/share/keyrings/
sudo apt update
sudo apt install -y cuda

echo ">>> Verifying NVIDIA GPU visibility..."
nvidia-smi || { echo "❌ ERROR: GPU not detected. Check instance type."; exit 1; }

echo ">>> Setting up Python virtual environment..."
python3 -m venv edgarenv
source edgarenv/bin/activate

echo ">>> Installing PyTorch with CUDA support..."
pip install --upgrade pip
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

echo ">>> Cloning EDGAR-Edge repo..."
# If you already uploaded it via SCP, skip this. Otherwise:
git clone https://github.com/YOUR_USERNAME/EDGAR-Edge.git
cd EDGAR-Edge

echo ">>> Installing project dependencies via Poetry..."
poetry install

echo "✅ Setup complete. Ready to fine-tune."

echo "💡 Next step: Upload your edgar_labels.parquet file to this instance."
echo "Then run: poetry run python src/research/finetune_roberta_script.py"
