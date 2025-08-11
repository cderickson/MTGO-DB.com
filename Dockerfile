FROM python:3.11-slim

# System deps for building wheels (psycopg2) and runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       gcc \
       libpq-dev \
       curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PORT=8080

# Install deps first to leverage Docker layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn

# Copy the rest of the app
COPY . .

EXPOSE 8080

# Default to web server; can be overridden by platform to run the worker
CMD ["gunicorn", "-w", "3", "-k", "gthread", "--threads", "8", "-b", "0.0.0.0:8080", "app:app"]