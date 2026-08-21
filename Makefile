.PHONY: dev backend-test frontend-test test seed

dev:
	./start.sh

seed:
	$(MAKE) -C server seed

backend-test:
	$(MAKE) -C server test
	cd server && python test_auth.py && python test_seeker.py && python test_ai_resilience.py && python test_billing.py && python test_evaluation.py && python test_interview.py && python test_support.py

frontend-test:
	cd web/tests && npm install && bash run-all.sh

test: backend-test frontend-test
