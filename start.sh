#!/bin/bash
# Career Pilot AI — Automatic startup script
# Starts both backend and frontend with one command

set -e

PROJECT_ROOT="/Users/santoshreddy/career-pilot.ai"
BACKEND_DIR="$PROJECT_ROOT/server"
FRONTEND_DIR="$PROJECT_ROOT/web"
BACKEND_PORT=8000
FRONTEND_PORT=3000

echo "🚀 Career Pilot AI — Starting all services..."
echo ""

# Check if ports are already in use
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        return 0  # Port in use
    else
        return 1  # Port available
    fi
}

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Stopping services..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    echo "✅ All services stopped"
    exit 0
}

trap cleanup EXIT INT TERM

# Start backend
if check_port $BACKEND_PORT; then
    echo "⚠️  Port $BACKEND_PORT is in use. Trying to kill existing process..."
    lsof -ti :$BACKEND_PORT | xargs kill -9 2>/dev/null || true
    sleep 1
fi

echo "📦 Starting Backend API (port $BACKEND_PORT)..."
cd "$BACKEND_DIR"
PYTHONPATH="$BACKEND_DIR" python -m uvicorn api.main:app --reload --port $BACKEND_PORT > /tmp/career-pilot-backend.log 2>&1 &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"
sleep 2

# Start frontend
if check_port $FRONTEND_PORT; then
    echo "⚠️  Port $FRONTEND_PORT is in use. Trying to kill existing process..."
    lsof -ti :$FRONTEND_PORT | xargs kill -9 2>/dev/null || true
    sleep 1
fi

echo "🌐 Starting Frontend Server (port $FRONTEND_PORT)..."
cd "$FRONTEND_DIR"
python3 -m http.server $FRONTEND_PORT --directory . > /tmp/career-pilot-frontend.log 2>&1 &
FRONTEND_PID=$!
echo "   Frontend PID: $FRONTEND_PID"
sleep 1

# Verify services are running
echo ""
echo "✅ All services started!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎯 Access your app:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "   🌐 Frontend:       http://localhost:$FRONTEND_PORT"
echo "   📡 Backend API:    http://localhost:$BACKEND_PORT"
echo "   📚 API Docs:       http://localhost:$BACKEND_PORT/docs"
echo "   💚 Health Check:   http://localhost:$BACKEND_PORT/health"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Logs:"
echo "   Backend:  tail -f /tmp/career-pilot-backend.log"
echo "   Frontend: tail -f /tmp/career-pilot-frontend.log"
echo ""
echo "🛑 To stop: Press Ctrl+C"
echo ""

# Keep script running
wait
