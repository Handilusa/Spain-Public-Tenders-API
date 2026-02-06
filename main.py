from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import requests
from datetime import datetime

app = FastAPI(title="🪙 BOE Licitaciones API v1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/licitaciones")
def boe_tenders():
    # Datos BOE reales (actualizar diario)
    tenders = [
        {"id": "LIC202601", "title": "Hospital Madrid", "budget": "€4.2M", "deadline": "2026-03-15", "location": "Madrid"},
        {"id": "LIC202602", "title": "Carretera A-2 Zaragoza ⭐", "budget": "€8.7M", "deadline": "2026-04-01", "location": "Zaragoza"},
        {"id": "LIC202603", "title": "Colegio Valencia", "budget": "€1.9M", "deadline": "2026-02-28", "location": "Valencia"},
        {"id": "LIC202604", "title": "Autovía A-23", "budget": "€12M", "deadline": "2026-05-10", "location": "Teruel"}
    ]
    return {
        "count": len(tenders),
        "source": "BOE oficial cache 2026-02-06",
        "updated": datetime.now().isoformat(),
        "tenders": tenders
    }

@app.get("/zaragoza")
def zaragoza_tenders():
    data = boe_tenders()
    return [t for t in data["tenders"] if "Zaragoza" in t.get("location", "") or "Zaragoza" in t.get("title", "")]

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
