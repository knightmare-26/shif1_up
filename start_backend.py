#!/usr/bin/env python3
"""
Startup script for Shif1 UP FastAPI backend.
Run from the project root directory: python start_backend.py
"""

import os
import sys
import subprocess
from pathlib import Path


def check_python_version():
    if sys.version_info < (3, 8):
        print(f"❌ Python 3.8+ required (got {sys.version.split()[0]})")
        sys.exit(1)
    print(f"✅ Python {sys.version.split()[0]}")


def check_dependencies():
    try:
        import fastapi
        import uvicorn
        print("✅ FastAPI and Uvicorn installed")
    except ImportError:
        print("📦 Installing dependencies...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            check=True,
        )
        print("✅ Dependencies installed")


def check_fastf1():
    try:
        import fastf1
        print("✅ FastF1 available")
        return True
    except ImportError:
        print("⚠️  FastF1 not installed — live/historical data will use fallbacks")
        print("   To install: pip install fastf1")
        return False


def setup_environment():
    os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    os.environ.setdefault("DUCKDB_PATH", "data/f1_history.duckdb")
    os.environ.setdefault("FASTF1_CACHE_DIR", "data/fastf1_cache")
    print("✅ Environment configured")


def create_directories():
    for d in ["data", "data/fastf1_cache", "data/telemetry"]:
        Path(d).mkdir(parents=True, exist_ok=True)
    print("✅ Data directories ready")


def start_backend():
    print("\n🚀 Starting Shif1 UP backend on http://localhost:8000")
    print("   Docs: http://localhost:8000/docs\n")
    # Add api/ to PYTHONPATH so `from services.xxx import ...` works when
    # uvicorn is launched from the project root with the `api.main:app` target.
    env = os.environ.copy()
    api_path = str(Path(__file__).parent / "api")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{api_path};{existing}" if existing else api_path
    try:
        subprocess.run(
            [sys.executable, "-m", "uvicorn", "api.main:app",
             "--host", "0.0.0.0", "--port", "8000", "--reload"],
            env=env,
            check=True,
        )
    except KeyboardInterrupt:
        print("\n🛑 Stopped")
    except subprocess.CalledProcessError as exc:
        print(f"\n❌ Backend failed to start: {exc}")
        sys.exit(1)


def main():
    print("🏁 Shif1 UP — Backend Startup")
    print("=" * 35)
    check_python_version()
    check_dependencies()
    check_fastf1()
    setup_environment()
    create_directories()
    start_backend()


if __name__ == "__main__":
    main()
