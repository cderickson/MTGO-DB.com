#!/usr/bin/env python3
"""
Start Flower for monitoring Celery tasks
"""

import os
import subprocess
import sys

def main():
    print("Starting Flower web monitoring for Celery tasks...")
    print("Once started, open http://localhost:5555 in your browser")
    
    # Set environment for local development
    os.environ['FLASK_ENV'] = 'local'
    
    # Start Flower
    try:
        subprocess.run([
            'celery', '-A', 'app.celery', 'flower',
            '--port=5555'
        ], check=True)
    except KeyboardInterrupt:
        print("\nFlower stopped.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to start Flower: {e}")
        return False
    except FileNotFoundError:
        print("Flower not found. Please install it with: pip install flower")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 