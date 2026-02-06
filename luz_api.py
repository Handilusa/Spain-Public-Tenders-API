from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import json
from pathlib import Path

app = FastAPI(
    title="Spain Electricity Prices API",
    description="Hourly electricity prices in Spain (PVPC), cleaned and normalized for apps and dashboards.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = Path("prices.json")

@app.get("/prices/today")
def get_today_prices():
    if not DATA_FILE.exists():
        return {"error": "No data yet. Run fetch_prices.py first."}
    with DATA_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return {"prices": data}

@app.get("/prices")
def get_prices():
    return {"endpoints": ["/prices/today"], "description": "Spain PVPC electricity prices"}

@app.get("/")
def root():
    return {
        "name": "Spain Electricity Prices API",
        "endpoints": ["/prices/today"],
        "data_source": "REE ESIOS (datos abiertos)",
        "pricing": "Available on RapidAPI"
    }
