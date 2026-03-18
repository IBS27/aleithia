.PHONY: setup-python dev-frontend dev-backend build-frontend test bootstrap-demo-data pipeline-smoke docker-up

setup-python:
	python3.12 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements-dev.txt

dev-frontend:
	cd frontend && npm run dev

dev-backend:
	cd backend && uvicorn main:app --reload

build-frontend:
	cd frontend && npm run build

test:
	pytest -q

bootstrap-demo-data:
	python scripts/bootstrap/bootstrap_demo_data.py

pipeline-smoke:
	python scripts/maintenance/test_pipelines.py

docker-up:
	docker-compose up --build
