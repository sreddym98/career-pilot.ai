#!/bin/bash
# Test and run ingestion with free job sources

echo "════════════════════════════════════════════════════════════════"
echo "🔍 Checking Free Job Source Configuration"
echo "════════════════════════════════════════════════════════════════"

missing=0

if [ -z "$USAJOBS_EMAIL" ]; then
    echo "⚠️  USAJOBS_EMAIL not set"
    missing=$((missing + 1))
else
    echo "✅ USAJOBS_EMAIL: $USAJOBS_EMAIL"
fi

if [ -z "$USAJOBS_KEY" ]; then
    echo "⚠️  USAJOBS_KEY not set"
    missing=$((missing + 1))
else
    echo "✅ USAJOBS_KEY: ${USAJOBS_KEY:0:10}..."
fi

if [ -z "$ADZUNA_APP_ID" ]; then
    echo "⚠️  ADZUNA_APP_ID not set"
    missing=$((missing + 1))
else
    echo "✅ ADZUNA_APP_ID: $ADZUNA_APP_ID"
fi

if [ -z "$ADZUNA_APP_KEY" ]; then
    echo "⚠️  ADZUNA_APP_KEY not set"
    missing=$((missing + 1))
else
    echo "✅ ADZUNA_APP_KEY: ${ADZUNA_APP_KEY:0:10}..."
fi

echo ""
echo "════════════════════════════════════════════════════════════════"

if [ $missing -gt 0 ]; then
    echo "❌ Missing $missing environment variables"
    echo ""
    echo "Quick setup:"
    echo "  export USAJOBS_EMAIL='your_email@example.com'"
    echo "  export USAJOBS_KEY='your_key_from_email'"
    echo "  export ADZUNA_APP_ID='your_app_id'"
    echo "  export ADZUNA_APP_KEY='your_app_key'"
    echo ""
    exit 1
else
    echo "✅ All environment variables configured!"
    echo ""
    echo "Running ingestion..."
    echo "════════════════════════════════════════════════════════════════"
    cd /Users/santoshreddy/career-pilot.ai
    python server/ingest/run.py --once
fi
