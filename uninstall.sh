#!/bin/bash
set -e

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${RED}${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${RED}${BOLD}║        MCP-PT UNINSTALL                  ║${NC}"
echo -e "${RED}${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}This will permanently remove:${NC}"
echo "  - All MCP-PT Docker containers, images, volumes, and networks"
echo "  - All scan data, session data, and configuration"
echo "  - The MCP-PT project directory ($(pwd))"
echo ""
echo -e "${GREEN}This will NOT touch:${NC}"
echo "  - Your SSH keys and ~/.ssh directory"
echo "  - Docker itself"
echo "  - Any other Docker containers/images/volumes"
echo "  - The rest of your operating system"
echo ""

# Require root or sudo
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root or with sudo.${NC}"
    exit 1
fi

# Confirm
read -p "$(echo -e ${RED}${BOLD})Are you sure you want to completely uninstall MCP-PT? [y/N] $(echo -e ${NC})" confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Uninstall cancelled."
    exit 0
fi

read -p "$(echo -e ${RED})Type 'UNINSTALL' to confirm: $(echo -e ${NC})" confirm2
if [ "$confirm2" != "UNINSTALL" ]; then
    echo "Uninstall cancelled."
    exit 0
fi

echo ""
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 1. Stop and remove containers
echo -e "${BOLD}[1/5] Stopping and removing Docker containers...${NC}"
if command -v docker &> /dev/null; then
    cd "$PROJECT_DIR"
    docker compose down 2>/dev/null || true
    # Remove containers by name in case compose down missed them
    for container in mcp-pt-backend mcp-pt-frontend mcp-pt-toolbox; do
        docker rm -f "$container" 2>/dev/null || true
    done
    echo -e "${GREEN}  Done${NC}"
else
    echo -e "${YELLOW}  Docker not found, skipping container removal${NC}"
fi

# 2. Remove Docker images
echo -e "${BOLD}[2/5] Removing Docker images...${NC}"
if command -v docker &> /dev/null; then
    for image in ptbudgetbuster-backend ptbudgetbuster-frontend ptbudgetbuster-toolbox; do
        docker rmi "$image" 2>/dev/null || true
    done
    echo -e "${GREEN}  Done${NC}"
fi

# 3. Remove Docker volumes
echo -e "${BOLD}[3/5] Removing Docker volumes...${NC}"
if command -v docker &> /dev/null; then
    for volume in ptbudgetbuster_scan-data ptbudgetbuster_tool-configs; do
        docker volume rm "$volume" 2>/dev/null || true
    done
    echo -e "${GREEN}  Done${NC}"
fi

# 4. Remove Docker network
echo -e "${BOLD}[4/5] Removing Docker network...${NC}"
if command -v docker &> /dev/null; then
    docker network rm ptbudgetbuster_mcp-pt-net 2>/dev/null || true
    echo -e "${GREEN}  Done${NC}"
fi

# 5. Remove the project directory
echo -e "${BOLD}[5/5] Removing project directory...${NC}"
if [ "$PROJECT_DIR" = "/" ] || [ "$PROJECT_DIR" = "/root" ]; then
    echo -e "${RED}  Safety check failed: refusing to delete $PROJECT_DIR${NC}"
    exit 1
fi

# Move out of the project dir before deleting it
cd /root
rm -rf "$PROJECT_DIR"
echo -e "${GREEN}  Removed $PROJECT_DIR${NC}"

echo ""
echo -e "${GREEN}${BOLD}MCP-PT has been completely uninstalled.${NC}"
echo ""
