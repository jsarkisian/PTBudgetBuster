#!/bin/bash
# PTBudgetBuster AWS EC2 Setup Script
# Run this on a fresh Amazon Linux 2023 or Ubuntu 22.04 EC2 instance.
#
# Prerequisites:
#   - EC2 instance with IAM role that has Bedrock permissions
#   - VPC endpoint for com.amazonaws.<region>.bedrock-runtime
#   - Security group: inbound 3000 (UI), 22 (SSH) from your IPs only
#
# Usage:
#   chmod +x aws-setup.sh
#   ./aws-setup.sh

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/jsarkisian/PTBudgetBuster.git}"
INSTALL_DIR="/opt/ptbudgetbuster"
AWS_REGION="${AWS_REGION:-us-east-1}"

echo "=== PTBudgetBuster AWS Setup ==="

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo "Cannot detect OS. Exiting."
    exit 1
fi

echo "[1/6] Installing Docker..."
if command -v docker &>/dev/null; then
    echo "  Docker already installed: $(docker --version)"
else
    if [ "$OS" = "amzn" ]; then
        sudo dnf update -y
        sudo dnf install -y docker git
        sudo systemctl enable docker
        sudo systemctl start docker
    elif [ "$OS" = "ubuntu" ]; then
        sudo apt-get update
        sudo apt-get install -y ca-certificates curl gnupg
        sudo install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        sudo chmod a+r /etc/apt/keyrings/docker.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        sudo apt-get update
        sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin git
        sudo systemctl enable docker
        sudo systemctl start docker
    else
        echo "Unsupported OS: $OS. Install Docker manually."
        exit 1
    fi
fi

echo "[2/6] Installing Docker Compose..."
if docker compose version &>/dev/null; then
    echo "  Docker Compose already available: $(docker compose version)"
else
    sudo mkdir -p /usr/local/lib/docker/cli-plugins
    COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep '"tag_name"' | cut -d'"' -f4)
    sudo curl -SL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-$(uname -m)" -o /usr/local/lib/docker/cli-plugins/docker-compose
    sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
fi

# Add current user to docker group
sudo usermod -aG docker "$USER" 2>/dev/null || true

echo "[3/6] Cloning repository..."
if [ -d "$INSTALL_DIR" ]; then
    echo "  $INSTALL_DIR already exists, pulling latest..."
    cd "$INSTALL_DIR"
    sudo git pull
else
    sudo git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi
sudo chown -R "$USER:$USER" "$INSTALL_DIR"

echo "[4/6] Configuring environment..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
    JWT_SECRET=$(openssl rand -hex 32)
    cat > "$INSTALL_DIR/.env" <<EOF
# PTBudgetBuster Configuration
AWS_REGION=${AWS_REGION}
BEDROCK_MODEL_ID=anthropic.claude-opus-4-6-v1
JWT_SECRET=${JWT_SECRET}
ALLOWED_ORIGINS=http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "localhost"):3000
BACKEND_PORT=8000
FRONTEND_PORT=3000
EOF
    echo "  Created .env with generated JWT_SECRET"
    echo "  Update ALLOWED_ORIGINS if using a domain name"
else
    echo "  .env already exists, skipping"
fi

echo "[5/6] Verifying IAM role has Bedrock access..."
if command -v aws &>/dev/null; then
    if aws bedrock list-foundation-models --region "$AWS_REGION" --query 'modelSummaries[?modelId==`anthropic.claude-opus-4-6-v1`].modelId' --output text 2>/dev/null | grep -q "anthropic"; then
        echo "  Bedrock access confirmed (Opus 4 available)"
    else
        echo "  WARNING: Could not verify Bedrock access."
        echo "  Ensure the EC2 IAM role has these permissions:"
        echo "    - bedrock:InvokeModel"
        echo "    - bedrock:InvokeModelWithResponseStream"
        echo "  And that Opus 4 model access is enabled in the Bedrock console."
    fi
else
    echo "  AWS CLI not found, installing..."
    if [ "$OS" = "amzn" ]; then
        sudo dnf install -y aws-cli
    elif [ "$OS" = "ubuntu" ]; then
        sudo apt-get install -y awscli
    fi
    echo "  Run 'aws bedrock list-foundation-models --region $AWS_REGION' to verify access"
fi

echo "[6/6] Building and starting containers..."
cd "$INSTALL_DIR"
sudo docker compose build
sudo docker compose up -d

echo ""
echo "=== Setup Complete ==="
echo ""
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "<your-ip>")
echo "Frontend:  http://${PUBLIC_IP}:3000"
echo "Backend:   http://${PUBLIC_IP}:8000/api/health"
echo ""
echo "Default admin credentials are created on first boot."
echo "Check logs: docker compose logs -f"
echo ""
echo "Next steps:"
echo "  1. Verify Bedrock model access is enabled in the AWS console"
echo "  2. Create a VPC endpoint for com.amazonaws.${AWS_REGION}.bedrock-runtime"
echo "  3. Update ALLOWED_ORIGINS in .env if using a domain name"
echo "  4. Consider adding HTTPS via a reverse proxy (nginx/caddy)"
