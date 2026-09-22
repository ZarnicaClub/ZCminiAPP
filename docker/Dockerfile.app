FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

# Сборочная сеть платформы не имеет маршрута IPv6: pip уходит на IPv6-адреса
# pypi.org/files.pythonhosted.org и падает с "[Errno 101] Network is unreachable".
# Заставляем резолвер предпочитать IPv4 (docker.io по IPv4 работает).
RUN printf 'precedence ::ffff:0:0/96  100\n' >> /etc/gai.conf

RUN pip install --no-cache-dir --retries 5 --timeout 60 -r requirements.txt

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
