#!/bin/bash
set -e

# -------- Configuration --------
AMI_ID="ami-084568db4383264d4"
INSTANCE_TYPE="g5.xlarge"
KEY_NAME="harrison2025"
SECURITY_GROUP_ID="sg-xxxxxxxx"      # <-- update
SUBNET_ID="subnet-xxxxxxxx"          # <-- update
IAM_INSTANCE_PROFILE="EdgarEdgeTrainingInstanceProfile"
REGION="us-east-1"
TAG="edgar-edge-gpu-training"
INSTANCE_NAME="edgar-edge-gpu"

# -------- Launch On-Demand Instance --------
echo ">>> Launching on-demand instance: $INSTANCE_TYPE in $REGION"

INSTANCE_ID=$(aws ec2 run-instances \
  --region "$REGION" \
  --image-id "$AMI_ID" \
  --count 1 \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --iam-instance-profile Name="$IAM_INSTANCE_PROFILE" \
  --block-device-mappings '[
        {
          "DeviceName": "/dev/sda1",
          "Ebs": {
            "VolumeSize": 100,
            "VolumeType": "gp3"
          }
        }
      ]' \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME},{Key=Project,Value=$TAG}]" \
  --query 'Instances[0].InstanceId' \
  --output text)

echo "✅ On-demand instance launched: $INSTANCE_ID"

# -------- Wait for Public IP --------
echo "⌛ Waiting for public IP..."

for i in {1..30}; do
  PUBLIC_IP=$(aws ec2 describe-instances \
    --region "$REGION" \
    --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)
  
  if [[ "$PUBLIC_IP" != "None" ]]; then
    break
  fi
  
  echo "Waiting..."
  sleep 5
done

if [[ "$PUBLIC_IP" == "None" || -z "$PUBLIC_IP" ]]; then
  echo "❌ Failed to get public IP."
  exit 1
fi

echo "🌐 Public IP: $PUBLIC_IP"
echo "🔐 SSH command:"
echo "    ssh -i ~/.ssh/${KEY_NAME}.pem ubuntu@${PUBLIC_IP}"
