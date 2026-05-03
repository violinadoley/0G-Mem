.PHONY: install test dev api proto clean lint tui bot demo da da-stop test-v format

install:
	pip install -e ".[dev]"
	npm install

dev:
	uvicorn api.main:app --reload --port 8000

da:
	docker-compose up -d

da-stop:
	docker-compose down

test:
	pytest tests/ -q

test-v:
	pytest tests/ -v

proto:
	bash scripts/generate_proto.sh

demo:
	export $$(grep -v "^\#" .env | grep -v "^$$" | xargs) && \
	python examples/legal_assistant.py

tui:
	export $$(grep -v "^\#" .env | grep -v "^$$" | xargs) && \
	TOKENIZERS_PARALLELISM=false python -m tui

bot:
	export $$(grep -v "^\#" .env | grep -v "^$$" | xargs) && \
	TOKENIZERS_PARALLELISM=false python -m telegram_bot

deploy:
	npx hardhat run contracts/scripts/deploy.js --network 0g-testnet

lint:
	ruff check ogmem/ api/ tests/

format:
	ruff format ogmem/ api/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache dist *.egg-info
	rm -f .ogmem_index_*.json audit_report.json
