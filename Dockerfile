FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

# All state lives in data/ — mount it as a volume so briefings/config/history
# survive redeploys:  -v trendradar_data:/app/data
VOLUME ["/app/data"]

ENV PYTHONUNBUFFERED=1
EXPOSE 5050

# Exactly ONE worker (in-memory cache — see wsgi.py); concurrency via threads.
# Timeout covers briefing generation; scrapes run in background threads anyway.
CMD ["gunicorn", "--workers", "1", "--threads", "8", "--timeout", "300", \
     "--bind", "0.0.0.0:5050", "wsgi:app"]
