.PHONY: install run run-all run-p1 run-p2 run-p3 run-p4 evals obs-up obs-down seed-github

install:
	pip install -e .

run:
	python main.py

run-all:
	python main.py --all

run-p1:
	python main.py --incident INC-2026-0145

run-p2:
	python main.py --incident INC-2026-0142

run-p3:
	python main.py --incident INC-2026-0143

run-p4:
	python main.py --incident INC-2026-0144

evals:
	arcade evals evals/ --details

obs-up:
	docker-compose -f observability/docker-compose.yml up -d

obs-down:
	docker-compose -f observability/docker-compose.yml down

seed-github:
	@echo "Run this from your pixelcorp-backend repo directory:"
	@echo "  python $(PWD)/seed/seed_github.py"
