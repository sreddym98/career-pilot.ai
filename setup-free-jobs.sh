#!/bin/bash
# Career Pilot — Free Job Sources Setup
# Sets up USAJOBS and ADZUNA free tier (no payment required)

set -e

echo "════════════════════════════════════════════════════════════════"
echo "🎯 FREE JOB SOURCES SETUP (No Payment)"
echo "════════════════════════════════════════════════════════════════"

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "\n${BLUE}Step 1: USAJOBS (Federal Jobs) — FREE${NC}"
echo "─────────────────────────────────────────"
echo "This adds 40-80+ federal IT and QA roles."
echo ""
read -p "Enter your email address for USAJOBS: " usajobs_email
if [ -z "$usajobs_email" ]; then
    echo "Email required. Skipping USAJOBS."
else
    echo -e "${YELLOW}Opening USAJOBS developer site...${NC}"
    echo "1. Go to: https://developer.usajobs.gov"
    echo "2. Click 'Sign Up'"
    echo "3. Enter your email: $usajobs_email"
    echo "4. You'll receive an API key via email"
    echo ""
    read -p "Enter your USAJOBS_KEY (from email): " usajobs_key
    if [ ! -z "$usajobs_key" ]; then
        export USAJOBS_EMAIL="$usajobs_email"
        export USAJOBS_KEY="$usajobs_key"
        echo -e "${GREEN}✓ USAJOBS configured${NC}"
    fi
fi

echo ""
echo -e "\n${BLUE}Step 2: ADZUNA (Free Tier) — FREE (1000 calls/month)${NC}"
echo "─────────────────────────────────────────"
echo "This adds 40-80+ mixed roles from aggregated boards."
echo ""
echo -e "${YELLOW}Opening ADZUNA...${NC}"
echo "1. Go to: https://www.adzuna.com/api/v1/applications"
echo "2. Click 'Add application'"
echo "3. Fill out form (any name, e.g., 'career-pilot')"
echo "4. You'll get app_id and app_key immediately"
echo ""
read -p "Enter your ADZUNA_APP_ID: " adzuna_app_id
if [ ! -z "$adzuna_app_id" ]; then
    read -p "Enter your ADZUNA_APP_KEY: " adzuna_app_key
    if [ ! -z "$adzuna_app_key" ]; then
        export ADZUNA_APP_ID="$adzuna_app_id"
        export ADZUNA_APP_KEY="$adzuna_app_key"
        echo -e "${GREEN}✓ ADZUNA configured${NC}"
    fi
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo -e "${GREEN}✨ Configuration Complete${NC}"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Add these to ~/.zshrc or ~/.bash_profile to persist:"
echo ""
if [ ! -z "$usajobs_key" ]; then
    echo "export USAJOBS_EMAIL=\"$usajobs_email\""
    echo "export USAJOBS_KEY=\"$usajobs_key\""
fi
if [ ! -z "$adzuna_app_id" ]; then
    echo "export ADZUNA_APP_ID=\"$adzuna_app_id\""
    echo "export ADZUNA_APP_KEY=\"$adzuna_app_key\""
fi
echo ""
echo "Then reload your shell:"
echo "  source ~/.zshrc"
echo ""
echo "Run ingestion:"
echo "  cd /Users/santoshreddy/career-pilot.ai"
echo "  python server/ingest/run.py --once"
echo ""
