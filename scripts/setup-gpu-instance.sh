#!/bin/bash
set -e

#Configured to run on vast.ai instance with Ubuntu 22.04, torch, and NVIDIA drivers pre-installed.
# Run from project root directory (EDGAR).

# Constants
# CUDA_DEB="cuda-repo-ubuntu2204-12-1-local_12.1.1-530.30.02-1_amd64.deb"
# CUDA_URL="https://developer.download.nvidia.com/compute/cuda/12.1.1/local_installers/$CUDA_DEB"

# --- CONFIGURATION VARIABLES ---
# AWS_ACCESS_KEY_ID="YOUR_ACCESS_KEY_ID"
# AWS_SECRET_ACCESS_KEY="YOUR_SECRET_ACCESS_KEY"
AWS_REGION="us-east-1"  # or your region
S3_URI="s3://edgar-edge-labelled-parquets/edgar_labels_sample_dataset.parquet"
DESTINATION_PATH="/workspace/EDGAR-edge/src/research"  # current directory, or change if needed
# -------------------------------

echo ">>> Updating system and installing base dependencies..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y git wget unzip tmux build-essential python3-pip python3-venv curl

echo ">>> Installing Python 3.12..."
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev


echo ">>> Installing Miniconda..."
MINICONDA_INSTALLER="Miniconda3-latest-Linux-x86_64.sh"
MINICONDA_URL="https://repo.anaconda.com/miniconda/$MINICONDA_INSTALLER"
wget $MINICONDA_URL -O /tmp/$MINICONDA_INSTALLER
bash /tmp/$MINICONDA_INSTALLER -b -p $HOME/miniconda3
rm /tmp/$MINICONDA_INSTALLER

echo ">>> Initializing Conda..."
source $HOME/miniconda3/bin/activate
conda init bash

echo ">>> Creating and activating Conda environment for research..."
# Navigate to the research directory first to ensure environment.yml is found
cd src/research/
conda env create -f environment.yml
conda activate edgar-research
cd ../../ # Navigate back to project root

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

echo ">>> Configuring AWS CLI..."
mkdir -p ~/.aws
cat <<EOF > ~/.aws/credentials
[default]
aws_access_key_id = $AWS_ACCESS_KEY_ID
aws_secret_access_key = $AWS_SECRET_ACCESS_KEY
EOF

cat <<EOF > ~/.aws/config
[default]
region = $AWS_REGION
output = json
EOF

echo ">>> Verifying AWS configuration..."
aws sts get-caller-identity

echo ">>> Downloading S3 object: $S3_URI"
aws s3 cp "$S3_URI" "$DESTINATION_PATH"

echo "✅ Done."

# echo ">>> Cloning EDGAR-Edge repo..."
# If you already uploaded it via SCP, skip this. Otherwise:
# git clone https://github.com/jackharrisonmohr/EDGAR-Edge
# cd EDGAR-Edge
echo "✅ Setup complete. Ready to fine-tune."

echo "💡 Next step: Upload your edgar_labels.parquet file to this instance (available with `curl -O https://edgar-edge-labelled-parquets.s3.us-east-1.amazonaws.com/edgar_labels_sample_dataset.parquet`)."
echo "Rename to `edgar_labels.parquet`"
echo "Then activate the conda environment and run the script:"
echo "conda activate edgar-research"
echo "python src/research/finetune_roberta_script.py"

# echo "download the dataset from se using: t "
