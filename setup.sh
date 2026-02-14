#!/bin/bash
set -e

echo "🛡️  PentestMCP Setup"
echo "===================="
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is required. Install it first:"
    echo "   curl -fsSL https://get.docker.com | sh"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose V2 is required."
    exit 1
fi

echo "✓ Docker and Docker Compose found"

# Create .env if not exists
if [ ! -f .env ]; then
    cp env.example .env
    echo ""
    echo "📝 Created .env file from template."
    echo "   You MUST set your Anthropic API key before starting."
    echo ""
    read -p "Enter your ANTHROPIC_API_KEY (or press Enter to set later): " api_key
    if [ -n "$api_key" ]; then
        sed -i "s|ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$api_key|" .env
        echo "✓ API key set"
    else
        echo "⚠️  Remember to set ANTHROPIC_API_KEY in .env before starting!"
    fi

    # Generate JWT secret
    jwt_secret=$(openssl rand -hex 32 2>/dev/null || head -c 64 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 64)
    sed -i "s|JWT_SECRET=.*|JWT_SECRET=$jwt_secret|" .env
    echo "✓ JWT secret generated"
else
    echo "✓ .env file exists"
fi

echo ""
echo "🔨 Building containers (this may take 5-10 minutes on first run)..."
docker compose build

echo ""
echo "🚀 Starting services..."
docker compose up -d

echo ""
echo "⏳ Waiting for services to be ready..."
sleep 10

# Health check
if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "✓ Backend is running"
else
    echo "⚠️  Backend may still be starting. Check: docker compose logs backend"
fi

echo ""
echo "════════════════════════════════════════"
echo "  PentestMCP is ready!"
echo "  Open: http://localhost:3000"
echo "════════════════════════════════════════"
echo ""
echo "Useful commands:"
echo "  docker compose logs -f        # View logs"
echo "  docker compose down            # Stop"
echo "  docker compose up -d           # Start"
echo "  docker compose build --no-cache # Rebuild"
