FROM python:3.12-slim

WORKDIR /app

# Зависимости лежат в репозитории (wheels/), установка идёт офлайн:
# сборочная сеть платформы не имеет доступа к pypi.org, поэтому --no-index.
COPY wheels ./wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=wheels -r requirements.txt

COPY shared ./shared
COPY crm ./crm
COPY orders_webhook ./orders_webhook
COPY app ./app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home appuser
USER appuser

EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
