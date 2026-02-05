#!/bin/bash
# =============================================================================
# He&She PG Backend - Deployment Script
# Run this after vps_setup.sh
# =============================================================================

set -e

APP_DIR="/var/www/heandshepg-backend"
REPO_URL="https://github.com/pallavireddy7890/heandshepg-backend.git"

echo "🚀 Deploying He&She PG Backend..."

# Navigate to app directory
cd $APP_DIR

# Clone or pull repository
if [ -d ".git" ]; then
    echo "📥 Pulling latest code..."
    git pull origin main
else
    echo "📥 Cloning repository..."
    git clone $REPO_URL .
fi

# Create virtual environment
echo "🐍 Setting up Python virtual environment..."
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Run database migrations
echo "🗄️ Running database migrations..."
alembic upgrade head
python run_migration.py

# Restart the service
echo "🔄 Restarting application service..."
sudo systemctl restart heandshepg

echo "✅ Deployment complete!"
echo "🌐 Your API is running at: https://heandshepg.com/api"
