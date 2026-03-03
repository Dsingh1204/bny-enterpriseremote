#!/bin/bash
# Quick Deploy Script for Cross-Network Testing
# Uses ngrok to create a public tunnel

echo "=============================================="
echo "  Enterprise Remote Support - Quick Deploy"
echo "=============================================="

# Check if ngrok is installed
if ! command -v ngrok &> /dev/null; then
    echo ""
    echo "ngrok not found. Install options:"
    echo ""
    echo "  macOS:   brew install ngrok"
    echo "  Linux:   snap install ngrok"
    echo "  Manual:  https://ngrok.com/download"
    echo ""
    exit 1
fi

# Start server in background
echo ""
echo "Starting server..."
cd server
npm start &
SERVER_PID=$!
sleep 3

# Start ngrok tunnel
echo ""
echo "Creating public tunnel with ngrok..."
echo ""
ngrok http 3000

# Cleanup on exit
trap "kill $SERVER_PID 2>/dev/null" EXIT
