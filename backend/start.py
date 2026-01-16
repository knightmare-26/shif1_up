#!/usr/bin/env python3
"""
Startup script for Shif1 UP FastAPI backend
"""

import os
import sys
import uvicorn
from pathlib import Path

def main():
    """Main startup function"""
    
    # Add the backend directory to Python path
    backend_dir = Path(__file__).parent
    sys.path.insert(0, str(backend_dir))
    
    # Set environment variables if not already set
    os.environ.setdefault("API_HOST", "0.0.0.0")
    os.environ.setdefault("API_PORT", "8000")
    os.environ.setdefault("API_RELOAD", "true")
    os.environ.setdefault("API_LOG_LEVEL", "info")
    
    # Get configuration from environment
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    reload = os.getenv("API_RELOAD", "true").lower() == "true"
    log_level = os.getenv("API_LOG_LEVEL", "info")
    
    print("🚀 Starting Shif1 UP FastAPI Backend...")
    print(f"📍 Host: {host}")
    print(f"🔌 Port: {port}")
    print(f"🔄 Reload: {reload}")
    print(f"📝 Log Level: {log_level}")
    print("=" * 50)
    
    # Start the server
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
        access_log=True
    )

if __name__ == "__main__":
    main()
