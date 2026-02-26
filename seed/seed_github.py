#!/usr/bin/env python3
"""
Seeds the pixelcorp-backend repo with realistic commit history.

Usage:
    cd /path/to/pixelcorp-backend
    python /path/to/bossbattle/seed/seed_github.py
    git push

The commits tell a story that ends with the "culprit" auth migration commit,
which is what BossBattle will identify as the root cause of INC-2026-0142.
"""

import subprocess
import os
import sys
from pathlib import Path


COMMITS = [
    ("fix: increase database connection pool size to 50", "config/database.yml",
     "max_connections: 50\npool_timeout: 30\nidle_timeout: 600\n"),
    ("feat: add Redis caching layer for user sessions", "services/cache.py",
     "import redis\n\nredis_client = redis.Redis(host='localhost', port=6379, db=0)\n\ndef cache_session(user_id, session_data, ttl=3600):\n    redis_client.setex(f'session:{user_id}', ttl, session_data)\n"),
    ("chore: upgrade postgres driver to v5.2.1", "requirements.txt",
     "psycopg2-binary==5.2.1\nredis==5.0.1\nfastapi==0.109.0\n"),
    ("fix: handle timeout in payment processing webhook", "services/payments.py",
     "import httpx\n\nTIMEOUT = 30\n\ndef process_webhook(payload):\n    try:\n        with httpx.Client(timeout=TIMEOUT) as client:\n            return client.post('/webhook', json=payload)\n    except httpx.TimeoutException:\n        raise PaymentTimeoutError('Webhook timed out')\n"),
    ("feat: add health check endpoint for k8s probes", "api/health.py",
     "from fastapi import APIRouter\n\nrouter = APIRouter()\n\n@router.get('/health')\ndef health_check():\n    return {'status': 'ok'}\n\n@router.get('/ready')\ndef readiness_check():\n    # Check DB and Redis connectivity\n    return {'status': 'ready'}\n"),
    ("fix: resolve memory leak in WebSocket handler", "services/websocket.py",
     "import weakref\n\n_connections = weakref.WeakSet()\n\ndef register_connection(ws):\n    _connections.add(ws)\n\ndef broadcast(message):\n    for conn in _connections:\n        conn.send(message)\n"),
    ("chore: update SSL certificates for Q1 2026", "certs/README.md",
     "# SSL Certificate Rotation\n\nCertificates rotated: 2026-02-01\nNext rotation: 2026-05-01\nManaged by: infra-team\n"),
    # This is the culprit commit for INC-2026-0142
    ("feat: migrate user auth to new OAuth provider", "services/auth.py",
     "# TODO: Migration in progress - legacy tokens may not validate\n# New provider: AuthCorp v2\nimport authcorp_v2 as auth\n\nPROVIDER_URL = 'https://auth.authcorp.io/v2'\n\ndef validate_token(token):\n    # WARNING: v2 API uses different token format\n    return auth.verify(token, provider=PROVIDER_URL)\n"),
    ("fix: add retry logic for external API calls", "utils/http_client.py",
     "import httpx\nfrom tenacity import retry, stop_after_attempt, wait_exponential\n\n@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))\ndef get_with_retry(url, **kwargs):\n    with httpx.Client() as client:\n        return client.get(url, **kwargs)\n"),
    ("docs: update runbook for database failover", "docs/runbooks/db-failover.md",
     "# Database Failover Runbook\n\n## Steps\n1. Check replica lag: `SELECT * FROM pg_stat_replication;`\n2. Promote replica: `pg_ctl promote -D /var/lib/postgresql/data`\n3. Update connection strings in Kubernetes secrets\n4. Notify team in #incidents\n"),
]


def run(cmd, cwd=None):
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {cmd}\n{result.stderr}")
        sys.exit(1)
    return result.stdout.strip()


def main():
    repo_dir = Path.cwd()

    # Verify we're in a git repo
    if not (repo_dir / ".git").exists():
        print("ERROR: Run this script from the root of your pixelcorp-backend git repo.")
        sys.exit(1)

    print(f"Seeding commits in: {repo_dir}")

    for message, filepath, content in COMMITS:
        full_path = repo_dir / filepath
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        run(f'git add "{filepath}"', cwd=repo_dir)
        run(f'git commit -m "{message}"', cwd=repo_dir)
        print(f"  ✓ {message}")

    print(f"\nDone. {len(COMMITS)} commits created.")
    print("Run `git push` to push to GitHub.")


if __name__ == "__main__":
    main()
