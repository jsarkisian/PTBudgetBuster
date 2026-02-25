#!/bin/bash
set -e

echo "🛡️  MCP-PT Setup"
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

# Check Tailscale
if command -v tailscale &> /dev/null; then
    ts_ip=$(tailscale ip -4 2>/dev/null)
    if [ -n "$ts_ip" ]; then
        echo "✓ Tailscale connected (IP: $ts_ip)"
        echo "  To bind MCP-PT to your tailnet only, set in .env:"
        echo "    FRONTEND_PORT=${ts_ip}:3000"
        echo "    BACKEND_PORT=${ts_ip}:8000"
        echo "    ALLOWED_ORIGINS=http://${ts_ip}:3000"
    else
        echo "⚠  Tailscale installed but not connected. Run: sudo tailscale up"
    fi
else
    echo "ℹ  Tailscale not installed (optional — see README for setup)"
fi

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
echo "  MCP-PT is ready!"
echo "  Open: http://localhost:3000"
echo "════════════════════════════════════════"

# Show admin credentials if this is the first run
admin_creds=$(docker compose logs backend 2>&1 | grep -A 4 "ADMIN CREDENTIALS" | grep "Password:" | head -1 | sed 's/.*Password: //')
if [ -n "$admin_creds" ]; then
    echo ""
    echo "  Admin Credentials (first run only):"
    echo "  ────────────────────────────────────"
    echo "  Username: admin"
    echo "  Password: $admin_creds"
    echo ""
    echo "  You will be required to change this"
    echo "  password on first login."
    echo "════════════════════════════════════════"
fi

echo ""
echo "Useful commands:"
echo "  docker compose logs -f        # View logs"
echo "  docker compose down            # Stop"
echo "  docker compose up -d           # Start"
echo "  docker compose build --no-cache # Rebuild"
