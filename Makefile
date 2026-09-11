.PHONY: install run test seed simulate

install:
	pip install -r requirements.txt

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

seed:
	python -m scripts.seed_synthetic_data

simulate:
	python -m scripts.simulate_offer_cycle
