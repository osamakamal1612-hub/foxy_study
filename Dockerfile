FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data COOKIE_SECURE=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
VOLUME /data
EXPOSE 8000
# ONE process with many threads (the study engine keeps state in memory)
CMD ["sh", "-c", "gunicorn -w 1 --threads 8 -t 180 -b 0.0.0.0:${PORT:-8000} app:app"]
