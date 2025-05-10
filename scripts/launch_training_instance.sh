#!/bin/bash
set -e

# -------- Configuration --------
AMI_ID="ami-0b8b44ec9a8f90422"        # Ubuntu 22.04 with NVIDIA driver support (update per region)
INSTANCE_TYPE="g5.xlarge"
KEY_NAME="harrison2025"              # Your uploaded AWS EC2 key pair name
SECURITY_GROUP_ID="sg-xxxxxxxx"      # Should allow SSH inbound (port 22)
SUBNET_ID="subnet-xxxxxxxx"          # Public or private subnet depending on access model
IAM_INSTANCE_PROFILE="EdgarEdgeTrainingInstanceProfile"  # Optional: gives S3 access etc.
SPOT_PRICE="0.20"                    # Max hourly price (adjust if needed)
REGION="us-east-1"
TAG="edgar-edge-gpu-training"
INSTANCE_NAME="edgar-edge-gpu"

# -------- Launch --------
echo ">>> Requesting spot instance: $INSTANCE_TYPE in $REGION"

aws ec2 request-spot-instances \
  --region "$REGION" \
  --spot-price "$SPOT_PRICE" \
  --instance-count 1 \
  --type "one-time" \
  --launch-specification "{
      \"ImageId\": \"$AMI_ID\",
      \"InstanceType\": \"$INSTANCE_TYPE\",
      \"KeyName\": \"$KEY_NAME\",
      \"SubnetId\": \"$SUBNET_ID\",
      \"SecurityGroupIds\": [\"$SECURITY_GROUP_ID\"],
      \"IamInstanceProfile\": {\"Name\": \"$IAM_INSTANCE_PROFILE\"},
      \"BlockDeviceMappings\": [
        {
          \"DeviceName\": \"/dev/sda1\",
          \"Ebs\": {
            \"VolumeSize\": 100,
            \"VolumeType\": \"gp3\"
          }
        }
      ],
      \"TagSpecifications\": [
        {
          \"ResourceType\": \"instance\",
          \"Tags\": [
            {\"Key\": \"Name\", \"Value\": \"$INSTANCE_NAME\"},
            {\"Key\": \"Project\", \"Value\": \"$TAG\"}
          ]
        }
      ]
    }"

echo "✅ Spot instance request submitted."
echo "👉 Go to AWS Console → EC2 → Spot Requests to monitor status."
echo "💡 Once fulfilled, SSH using:"
echo "    ssh -i ~/.ssh/${KEY_NAME}.pem ubuntu@<public-ip>"
