#!/bin/bash
# =============================================================================
# He&She PG Backend - VPS Setup Script
# Run this on a fresh Ubuntu VPS
# =============================================================================

set -e

echo "🚀 Starting He&She PG Backend Setup..."

# Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install Python 3.11
echo "🐍 Installing Python 3.11..."
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

# Install PostgreSQL
echo "🗄️ Installing PostgreSQL..."
sudo apt install -y postgresql postgresql-contrib

# Install Nginx
echo "🌐 Installing Nginx..."
sudo apt install -y nginx

# Install Git
echo "📥 Installing Git..."
sudo apt install -y git

# Install Certbot for SSL
echo "🔒 Installing Certbot..."
sudo apt install -y certbot python3-certbot-nginx

# Create app directory
echo "📁 Creating application directory..."
sudo mkdir -p /var/www/heandshepg-backend
sudo chown $USER:$USER /var/www/heandshepg-backend

echo "✅ System dependencies installed!"
echo ""
echo "Next steps:"
echo "1. Clone your repository"
echo "2. Set up PostgreSQL database"
echo "3. Configure environment variables"
echo "4. Run deploy.sh"
