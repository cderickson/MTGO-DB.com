# Local Development Directory

This directory contains all files and configurations specific to local development.

## Directory Structure

```
local/
├── README.md                    # This file
├── local_config.cfg            # Local development configuration
├── requirements-local.txt      # Local development dependencies
├── setup_local.py              # Local development setup script
├── start_celery.py             # Script to start Celery worker
├── LOCAL_DEVELOPMENT.md        # Detailed local development guide
└── data/                       # Local data storage
    ├── uploads/                # File uploads (local storage)
    └── logs/                   # Application logs
```

## Quick Start

### Option 1: Start Everything at Once (Recommended)
```bash
python local-dev/start_all.py
```
This starts Flask app, Celery worker, and Flower monitor in one command!

### Option 2: Manual Start (3 separate terminals)
1. **Celery Worker**: `python local-dev/start_celery.py` 
2. **Flask App**: `python app.py`
3. **Flower Monitor**: `python local-dev/start_flower.py` (optional)

## Configuration

Edit `local_config.cfg` to customize your local development environment:
- Database settings (SQLite)
- Email settings (for testing)
- Redis settings
- Local secrets

## Data Storage

- **Uploads**: Files uploaded during development are stored in `data/uploads/`
- **Logs**: Application logs are stored in `data/logs/`
- **Database**: SQLite database is created in the project root as `local_database.db`

## Benefits of This Structure

- ✅ **Clean separation** between local and production files
- ✅ **Easy to ignore** local files in version control
- ✅ **Organized data** storage for development
- ✅ **Clear documentation** for local setup
- ✅ **Production-ready** root directory structure 