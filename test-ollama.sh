#!/bin/bash

# Test Ollama Integration - Resume Builder and AI Endpoints

echo "🧪 Testing Ollama Integration"
echo "================================"
echo ""

# Test 1: Health check
echo "1️⃣  Backend Health Check"
HEALTH=$(curl -s http://localhost:8000/health)
echo "Response: $HEALTH"
echo ""

# Test 2: Simple AI tailor endpoint
echo "2️⃣  AI Tailor Endpoint (Simple JSON)"
RESPONSE=$(curl -s -X POST http://localhost:8000/api/ai/tailor \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Return valid JSON: {\"test\": true}","max_tokens":50}')
echo "Response: $RESPONSE"
echo ""

# Test 3: Resume-like prompt
echo "3️⃣  Resume Builder Style Prompt"
RESUME_PROMPT='Create a JSON object for this role: {
  "role": "Senior Backend Engineer",
  "company": "TechCorp",
  "bullets": ["Built microservices", "Led team of 5"],
  "years": 3
}'

RESPONSE=$(curl -s -X POST http://localhost:8000/api/ai/tailor \
  -H "Content-Type: application/json" \
  -d "{\"prompt\":\"$RESUME_PROMPT\",\"max_tokens\":200,\"label\":\"test-role\"}")
echo "Response: $RESPONSE"
echo ""

# Test 4: Cover Letter Prompt Style
echo "4️⃣  Cover Letter Style Prompt"
COVER_PROMPT='Generate a brief professional intro. Return ONLY JSON: {"intro": "..."}'

RESPONSE=$(curl -s -X POST http://localhost:8000/api/ai/tailor \
  -H "Content-Type: application/json" \
  -d "{\"prompt\":\"$COVER_PROMPT\",\"max_tokens\":150}")
echo "Response: $RESPONSE"
echo ""

# Test 5: Check Ollama directly
echo "5️⃣  Direct Ollama Check"
OLLAMA_TEST=$(curl -s -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"mistral","prompt":"Say hello as JSON: {\"greeting\": \"hello\"}","stream":false}')
echo "Response: $OLLAMA_TEST" | jq -r '.response' 2>/dev/null || echo "$OLLAMA_TEST"
echo ""

echo "✅ Tests Complete"
echo "If all responses are valid JSON, Ollama integration is working!"
