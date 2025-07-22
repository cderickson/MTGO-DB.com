#!/usr/bin/env python3
"""
Start all development services for MTGO-DB
"""

import os
import subprocess
import sys
import time

def main():
    print("🚀 Starting MTGO-DB Development Environment...")
    print("=" * 50)
    
    # Set environment for local development
    os.environ['FLASK_ENV'] = 'local'
    
    processes = []
    
    try:
        # Start Celery Worker
        print("📦 Starting Celery Worker...")
        celery_process = subprocess.Popen([
            sys.executable, 'local-dev/start_celery.py'
        ], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        processes.append(('Celery Worker', celery_process))
        time.sleep(2)  # Give it time to start
        
        # Start Flower Monitor
        print("🌸 Starting Flower Monitor...")
        flower_process = subprocess.Popen([
            sys.executable, 'local-dev/start_flower.py'
        ], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        processes.append(('Flower Monitor', flower_process))
        time.sleep(2)  # Give it time to start
        
        # Start Flask App
        print("🌐 Starting Flask App...")
        flask_process = subprocess.Popen([
            sys.executable, 'app.py'
        ], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        processes.append(('Flask App', flask_process))
        
        print("\n" + "=" * 50)
        print("✅ All services started!")
        print("=" * 50)
        print("🌐 Flask App:    http://localhost:8000")
        print("🌸 Flower:       http://localhost:5555")
        print("📊 Task Monitor: http://localhost:8000/tasks")
        print("=" * 50)
        print("\n💡 Press Ctrl+C to stop all services")
        
        # Wait for keyboard interrupt
        while True:
            time.sleep(1)
            # Check if any process has died
            for name, process in processes:
                if process.poll() is not None:
                    print(f"⚠️  {name} has stopped unexpectedly!")
                    
    except KeyboardInterrupt:
        print("\n🛑 Stopping all services...")
        
        # Terminate all processes
        for name, process in processes:
            print(f"🔄 Stopping {name}...")
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            except Exception as e:
                print(f"❌ Error stopping {name}: {e}")
        
        print("✅ All services stopped!")
        
    except Exception as e:
        print(f"❌ Error starting services: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 