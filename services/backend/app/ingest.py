from fastapi import FastAPI
from fastapi.responses import PlainTextResponse


app = FastAPI(title="SAMoparser Ingest")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    return "# SAMoparser ingest metrics placeholder\n"
