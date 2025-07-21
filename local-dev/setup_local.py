#!/usr/bin/env python3
"""
Local development setup script for MTGO-DB Flask application
"""

import os
import subprocess
import sys

def run_command(command, description):
    """Run a command and handle errors"""
    print(f"\n{description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✓ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} failed:")
        print(f"Error: {e.stderr}")
        return False

def create_directories():
    """Create necessary directories"""
    directories = ['local/data/uploads', 'local/data/logs']
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"✓ Created directory: {directory}")

def check_redis():
    """Check if Redis is running"""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        print("✓ Redis is running")
        return True
    except Exception as e:
        print("✗ Redis is not running or not accessible")
        print("Please install and start Redis:")
        print("  Windows: Download from https://redis.io/download")
        print("  macOS: brew install redis && brew services start redis")
        print("  Linux: sudo apt-get install redis-server && sudo systemctl start redis")
        return False

def main():
    print("Setting up MTGO-DB for local development...")
    
    # Create necessary directories
    create_directories()
    
    # Install dependencies
    if not run_command("pip install -r local/requirements-local.txt", "Installing Python dependencies"):
        print("Failed to install dependencies. Please check your Python environment.")
        return False
    
    # Check Redis
    if not check_redis():
        print("\n⚠️  Warning: Redis is required for Celery background tasks.")
        print("The app will still run, but background tasks won't work.")
    
    print("\n🎉 Setup complete!")
    print("\nTo run the application locally:")
    print("1. Make sure Redis is running (for background tasks)")
    print("2. Update local/local_config.cfg with your settings")
    print("3. Run: python app.py")
    print("4. Open http://localhost:8000 in your browser")
    
    print("\nFor AWS deployment preparation:")
    print("1. Update static/config.cfg for production settings")
    print("2. Set environment variables for production")
    print("3. Use requirements.txt for production dependencies")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 