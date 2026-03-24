#!/bin/bash
# Create VPC Endpoint for Bedrock Runtime
# This keeps AI API calls within your VPC — no public internet.
#
# Run this from your local machine with AWS CLI configured,
# or from the EC2 instance itself.
#
# Usage:
#   chmod +x vpc-endpoint-setup.sh
#   ./vpc-endpoint-setup.sh

set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"

echo "=== Bedrock VPC Endpoint Setup ==="

# Get the VPC and subnet of the running instance
echo "[1/4] Detecting VPC and subnet..."
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
VPC_ID=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --region "$AWS_REGION" \
    --query 'Reservations[0].Instances[0].VpcId' --output text)
SUBNET_ID=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --region "$AWS_REGION" \
    --query 'Reservations[0].Instances[0].SubnetId' --output text)
SG_ID=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --region "$AWS_REGION" \
    --query 'Reservations[0].Instances[0].SecurityGroups[0].GroupId' --output text)

echo "  VPC:    $VPC_ID"
echo "  Subnet: $SUBNET_ID"
echo "  SG:     $SG_ID"

# Check if endpoint already exists
echo "[2/4] Checking for existing endpoint..."
EXISTING=$(aws ec2 describe-vpc-endpoints --region "$AWS_REGION" \
    --filters "Name=vpc-id,Values=$VPC_ID" "Name=service-name,Values=com.amazonaws.${AWS_REGION}.bedrock-runtime" \
    --query 'VpcEndpoints[0].VpcEndpointId' --output text 2>/dev/null || echo "None")

if [ "$EXISTING" != "None" ] && [ -n "$EXISTING" ]; then
    echo "  Endpoint already exists: $EXISTING"
    echo "  Done."
    exit 0
fi

# Create security group for the endpoint
echo "[3/4] Creating security group for endpoint..."
EP_SG_ID=$(aws ec2 create-security-group \
    --group-name "bedrock-endpoint-sg" \
    --description "Allow HTTPS from EC2 to Bedrock VPC endpoint" \
    --vpc-id "$VPC_ID" \
    --region "$AWS_REGION" \
    --query 'GroupId' --output text)

aws ec2 authorize-security-group-ingress \
    --group-id "$EP_SG_ID" \
    --protocol tcp \
    --port 443 \
    --source-group "$SG_ID" \
    --region "$AWS_REGION"

echo "  Created SG: $EP_SG_ID"

# Create the VPC endpoint
echo "[4/4] Creating VPC endpoint for Bedrock Runtime..."
ENDPOINT_ID=$(aws ec2 create-vpc-endpoint \
    --vpc-id "$VPC_ID" \
    --vpc-endpoint-type Interface \
    --service-name "com.amazonaws.${AWS_REGION}.bedrock-runtime" \
    --subnet-ids "$SUBNET_ID" \
    --security-group-ids "$EP_SG_ID" \
    --private-dns-enabled \
    --region "$AWS_REGION" \
    --query 'VpcEndpoint.VpcEndpointId' --output text)

echo ""
echo "=== VPC Endpoint Created ==="
echo "Endpoint ID: $ENDPOINT_ID"
echo ""
echo "Private DNS is enabled — boto3 will automatically route"
echo "bedrock-runtime.${AWS_REGION}.amazonaws.com through the VPC endpoint."
echo "No code changes needed."
echo ""
echo "It may take 1-2 minutes for the endpoint to become available."
echo "Check status: aws ec2 describe-vpc-endpoints --vpc-endpoint-ids $ENDPOINT_ID --region $AWS_REGION"
