#!/bin/bash
# Simple local development server for testing Career Pilot AI
# Run this in the web/ directory to serve the frontend via HTTP

cd "$(dirname "$0")"
echo "Starting local development server..."
echo "Frontend: http://localhost:3000"
echo "Backend:  http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Python 3 - built-in HTTP server
python3 -m http.server 3000 --directory .
