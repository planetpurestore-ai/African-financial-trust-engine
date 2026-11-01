import os
import subprocess
import sys


def test_production_refuses_to_start_without_managed_database_url():
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env["APP_ENV"] = "production"
    result = subprocess.run(
        [sys.executable, "-c", "import app.production_db"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "DATABASE_URL is required when APP_ENV=production" in result.stderr
