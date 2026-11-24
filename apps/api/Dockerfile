FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app
COPY apps/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY apps/api/app ./app
COPY agents ./agents
COPY tools/public_apis ./tools/public_apis
COPY data/external ./data/external
COPY apps/api/alembic.ini ./apps/api/alembic.ini
COPY apps/api/migrations ./apps/api/migrations
COPY db/seeds ./db/seeds
COPY data/fixtures/kg-demo-01 ./data/fixtures/kg-demo-01
COPY apps/api/entrypoint.sh ./apps/api/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["bash", "/app/apps/api/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
