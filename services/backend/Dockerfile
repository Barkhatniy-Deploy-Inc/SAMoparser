FROM python:3.12.8-slim-bookworm

RUN groupadd --system --gid 10001 sam && useradd --system --uid 10001 --gid 10001 --create-home sam
WORKDIR /app

COPY services/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=sam:sam services/backend ./services/backend

ENV PYTHONPATH=/app/services/backend
USER sam

CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
