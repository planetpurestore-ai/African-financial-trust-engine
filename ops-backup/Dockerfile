FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backup_server.py /app/backup_server.py
ENV PYTHONUNBUFFERED=1
CMD ["python", "/app/backup_server.py"]
