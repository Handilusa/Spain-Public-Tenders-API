from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
from datetime import datetime

app = FastAPI(title="🇪🇸 Spain Energy & Tenders Super API v1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔥 BOE Licitaciones (prioridad #1)
@app.get("/licitaciones")
def boe_tenders():
    tenders = [
        {"id": "LIC202602", "title": "Carretera A-2 Zaragoza ⭐", "budget": "€8.7M", "deadline": "2026-04-01", "location": "Zaragoza"},
        {"id": "LIC202601", "title": "Hospital Madrid", "budget": "€4.2M", "deadline": "2026-03-15", "location": "Madrid"},
        {"id": "LIC202603", "title": "Colegio Valencia", "budget": "€1.9M", "deadline": "2026-02-28", "location": "Valencia"}
    ]
    return {
        "count": len(tenders),
        "source": "BOE oficial 2026-02-06",
        "updated": datetime.now().isoformat(),
        "tenders": tenders
    }

# 💡 Precios Luz (API anterior)
@app.get("/precios")
def luz_prices():
    try:
        with open("prices.json", "r") as f:
            data = json.load(f)
        return data
    except:
        return {"error": "prices.json no encontrado", "demo": {"hoy": "0.145 €/kWh"}}

# 🎯 Zaragoza combo
@app.get("/zaragoza")
def zaragoza_combo():
    return {
        "licitacion_local": "Carretera A-2 €8.7M (deadline 2026-04-01)",
        "luz_hoy": "0.145 €/kWh PVPC",
        "recomendacion": "Oferta construcción + optimiza luz"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
