FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY painel.py .
COPY assets/ assets/

EXPOSE 8000

CMD ["gunicorn", "--bind=0.0.0.0:8000", "--timeout", "600", "--workers", "2", "painel:server"]
