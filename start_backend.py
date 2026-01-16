#!/usr/bin/env python3
"""
Startup script for Shif1 UP FastAPI backend
Run this from the project root directory
"""

import os
import sys
import subprocess
import time
from pathlib import Path

def check_python_version():
    """Check if Python version is compatible"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        print(f"Current version: {sys.version}")
        sys.exit(1)
    print(f"✅ Python version: {sys.version.split()[0]}")

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import fastapi
        import uvicorn
        print("✅ FastAPI and Uvicorn are installed")
    except ImportError:
        print("❌ FastAPI or Uvicorn not found")
        print("Installing dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "backend/requirements.txt"])
        print("✅ Dependencies installed")

def check_fastf1():
    """Check if FastF1 is available"""
    try:
        import fastf1
        print("✅ FastF1 is available")
        return True
    except ImportError:
        print("⚠️ FastF1 not available - will use mock data")
        print("To install FastF1: pip install fastf1")
        return False

def setup_environment():
    """Set up environment variables"""
    os.environ.setdefault("API_HOST", "0.0.0.0")
    os.environ.setdefault("API_PORT", "8000")
    os.environ.setdefault("API_RELOAD", "true")
    os.environ.setdefault("API_LOG_LEVEL", "info")
    os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    
    print("✅ Environment variables set")

def create_directories():
    """Create necessary directories"""
    directories = [
        "backend/cache",
        "backend/fastf1_cache"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    print("✅ Directories created")

def start_backend():
    """Start the FastAPI backend"""
    print("\n🚀 Starting Shif1 UP FastAPI Backend...")
    print("=" * 50)
    
    # Change to backend directory
    backend_dir = Path(__file__).parent / "backend"
    os.chdir(backend_dir)
    
    # Start the server
    try:
        subprocess.run([
            sys.executable, "start.py"
        ], check=True)
    except KeyboardInterrupt:
        print("\n🛑 Backend stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Backend failed to start: {e}")
        sys.exit(1)

def main():
    """Main startup function"""
    print("🏁 Shif1 UP Backend Startup")
    print("=" * 30)
    
    # Pre-flight checks
    check_python_version()
    check_dependencies()
    fastf1_available = check_fastf1()
    setup_environment()
    create_directories()
    
    print(f"\n📊 FastF1 Status: {'Available' if fastf1_available else 'Mock Data Only'}")
    print("🌐 API will be available at: http://localhost:8000")
    print("📚 Documentation: http://localhost:8000/docs")
    print("🔄 Auto-reload: Enabled")
    
    # Start the backend
    start_backend()

if __name__ == "__main__":
    main()
