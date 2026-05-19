FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY painel.py .
COPY assets/ assets/

EXPOSE 10000

CMD ["sh", "-c", "exec gunicorn --bind=0.0.0.0:${PORT:-8000} --timeout 600 --workers 2 painel:server"]
