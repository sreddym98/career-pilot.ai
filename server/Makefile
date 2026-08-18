.PHONY: setup dev seed test clean

setup:
	pip install -r requirements.txt
	python seed.py

dev:
	uvicorn api.main:app --reload --port 8000

seed:
	python seed.py

test:
	python ingest/visa_parse.py
	@echo ""
	@API=http://localhost:8000 bash test_api.sh

verify:
	python ingest/verify_slugs.py

verify-fix:
	python ingest/verify_slugs.py --fix

ingest:
	python ingest/ingest.py --run

report:
	python ingest/ingest.py --report

clean:
	rm -f dev.db

stripe-setup:
	python setup_stripe.py

stripe-listen:
	stripe listen --forward-to localhost:8000/api/billing/webhook

ingest-once:
	python ingest/run.py --once

ingest-fast:
	python ingest/run.py --fast

ingest-loop:
	python ingest/run.py --loop

board:
	python ingest/run.py --report
