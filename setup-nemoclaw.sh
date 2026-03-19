#!/bin/bash
# Run on remote Brev instance to set up NemoClaw executor node

set -e

echo "=== NemoClaw Executor Node Setup ==="

# Install NemoClaw
export PATH="$HOME/.local/bin:$PATH"
echo "Installing NemoClaw..."
curl -fsSL https://nvidia.com/nemoclaw.sh | bash

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install fastapi uvicorn httpx python-dotenv openai

# Download nemoclaw-server.py from orchestrator
ORCHESTRATOR_URL="${ORCHESTRATOR_URL:-http://main:8080}"
echo "Downloading nemoclaw-server.py from $ORCHESTRATOR_URL..."
curl -fsSL "$ORCHESTRATOR_URL/static/nemoclaw-server.py" -o /root/nemoclaw-server.py

# Generate unique node ID
NODE_ID=$(uuidgen | cut -c1-8)
echo "NODE_ID=$NODE_ID" > /root/.nemoclaw.env

# Configure environment
cat >> /root/.nemoclaw.env << EOF
ORCHESTRATOR_URL=$ORCHESTRATOR_URL
NODE_NAME=$(hostname)
NVIDIA_API_KEY=${NVIDIA_API_KEY}
PORT=9000
EOF

# Create systemd service
cat > /etc/systemd/system/nemoclaw-executor.service << EOF
[Unit]
Description=NemoClaw Executor Node
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
EnvironmentFile=/root/.nemoclaw.env
ExecStart=/usr/bin/python3 -m uvicorn nemoclaw-server:app --host 0.0.0.0 --port 9000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Start service
systemctl daemon-reload
systemctl enable nemoclaw-executor
systemctl start nemoclaw-executor

echo "=== Setup Complete ==="
echo "Node ID: $NODE_ID"
echo "Status: systemctl status nemoclaw-executor"
echo "Logs: journalctl -u nemoclaw-executor -f"
