from fastapi import FastAPI
from fastapi.responses import PlainTextResponse


app = FastAPI(
    title="SAMoparser — сервис загрузки данных",
    description="Сервис приёма данных об установленных программах и источниках инвентаризации.",
    version="1.0.0",
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    return "# SAMoparser ingest metrics placeholder\n"
