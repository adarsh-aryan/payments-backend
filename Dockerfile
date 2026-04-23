# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app ./app

ENV PORT=8080
EXPOSE 8080

# Use shell form to allow $PORT substitution on Render/Heroku-like environments
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
