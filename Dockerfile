FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY VERSION ./VERSION
COPY pytest.ini ./pytest.ini
COPY Dockerfile ./Dockerfile
COPY docker-compose.yml ./docker-compose.yml
COPY ontology ./ontology
COPY src ./src
COPY config ./config
COPY sql ./sql
COPY docs ./docs
COPY tests ./tests
COPY scripts ./scripts

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
