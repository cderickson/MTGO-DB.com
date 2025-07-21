#!/usr/bin/env python3
"""
Start Celery worker for local development
"""

import os
import subprocess
import sys

def main():
    print("Starting Celery worker for local development...")
    
    # Set environment for local development
    os.environ['FLASK_ENV'] = 'local'
    
    # Start Celery worker
    try:
        subprocess.run([
            'celery', '-A', 'app.celery', 'worker',
            '--loglevel=info',
            '--concurrency=1'
        ], check=True)
    except KeyboardInterrupt:
        print("\nCelery worker stopped.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to start Celery worker: {e}")
        return False
    except FileNotFoundError:
        print("Celery not found. Please install it with: pip install celery")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 