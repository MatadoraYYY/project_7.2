.PHONY: install seed reseed simulate run test docker-build docker-up clean

install:
	pip install -r requirements.txt
	cp -n .env.example .env || true

seed:
	python -m scripts.seed_synthetic_data

reseed:
	python -m scripts.seed_synthetic_data --reset
	python -m scripts.simulate_offer_cycle --reset

simulate:
	python -m scripts.simulate_offer_cycle

run:
	uvicorn app.main:app --reload

test:
	pytest tests/ -v

docker-build:
	docker compose build

docker-up:
	docker compose up -d

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
