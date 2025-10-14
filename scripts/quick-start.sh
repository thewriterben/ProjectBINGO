#!/bin/bash
# ProjectBINGO Quick Start Script

set -e

echo "========================================="
echo "ProjectBINGO Quick Start"
echo "========================================="

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed"
    exit 1
fi

echo "✓ Starting services with Docker Compose..."
docker-compose up -d

echo "✓ Waiting for services..."
sleep 10

echo ""
echo "Services are ready!"
echo "  API Gateway: http://localhost:3000"
echo ""
echo "Quick start complete! 🚀"
