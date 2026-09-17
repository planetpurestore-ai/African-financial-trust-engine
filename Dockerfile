FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --home-dir /app app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
RUN chown -R app:app /app
USER app
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT','10000'), timeout=4)" || exit 1
CMD ["sh", "-c", "python -c \"p='app/dashboard_v2.html';s=open(p).read();t=open('app/premium_dark_theme.css').read();m='<!-- PREMIUM-DARK-PIXEL-PASS -->';s=s if m in s else s.replace('</head>',m+'<style>'+t+'</style></head>',1);open(p,'w').write(s)\" && alembic upgrade head && python -m app.bootstrap_runtime && exec uvicorn app.production_entry:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
