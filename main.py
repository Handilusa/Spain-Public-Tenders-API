from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
import uvicorn
from datetime import datetime, date, timedelta
from statistics import mean
from typing import Dict, List

app = FastAPI(
    title="⚡ Spain Energy PVPC API (ESIOS Direct)",
    description="API real de precios PVPC España directamente de ESIOS REE",
    version="4.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Indicadores ESIOS: 1001 (PCB), 1002 (Ceuta/Melilla)
ESIOS_BASE = "https://api.esios.ree.es/indicators"
INDICATOR_PCB = 1001
INDICATOR_CM = 1002

def fetch_esios_pvpc(day: date, zone: str) -> Dict:
    """Obtiene precios PVPC de ESIOS REE para un día y zona"""
    indicator = INDICATOR_PCB if zone.lower() == "pcb" else INDICATOR_CM
    
    start_date = day.strftime("%Y-%m-%dT00:00:00")
    end_date = (day + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")
    
    url = f"{ESIOS_BASE}/{indicator}"
    params = {
        "start_date": start_date,
        "end_date": end_date
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        hourly = {}
        for entry in data.get("indicator", {}).get("values", []):
            dt = datetime.fromisoformat(entry["datetime"].replace("Z", "+00:00"))
            hour = dt.hour
            price_mwh = float(entry["value"])
            price_kwh = round(price_mwh / 1000, 5)
            hourly[hour] = price_kwh
        
        if not hourly:
            raise HTTPException(503, detail="No hay datos PVPC disponibles para este día")
        
        return {
            "date": day,
            "zone": zone.upper(),
            "hourly": hourly
        }
    
    except requests.RequestException as e:
        raise HTTPException(503, detail=f"Error conectando con ESIOS: {str(e)}")

def calculate_stats(prices: List[float]) -> Dict:
    """Calcula estadísticas de lista de precios"""
    if not prices:
        return {"min": 0, "max": 0, "avg": 0}
    return {
        "min": round(min(prices), 5),
        "max": round(max(prices), 5),
        "avg": round(mean(prices), 5)
    }

@app.get("/")
def root():
    """Endpoint raíz con información de la API"""
    return {
        "api": "⚡ Spain Energy PVPC API (ESIOS Direct)",
        "version": "4.0.0",
        "status": "✅ LIVE",
        "data_source": "ESIOS REE directo (sin intermediarios)",
        "endpoints": [
            "/now?zone=pcb - Precio actual",
            "/today?zone=pcb - Precios 24h hoy",
            "/forecast?zone=pcb - Predicción 6h",
            "/stats?zone=pcb - Estadísticas día",
            "/cheapest?zone=pcb&limit=5 - Horas baratas"
        ],
        "zones": ["pcb (Península/Canarias/Baleares)", "cm (Ceuta/Melilla)"],
        "docs": "/docs"
    }

@app.get("/now")
def get_current_price(zone: str = "pcb"):
    """Precio actual de la luz en tiempo real"""
    today = date.today()
    data = fetch_esios_pvpc(today, zone)
    
    current_hour = datetime.now().hour
    hourly = data["hourly"]
    
    if current_hour not in hourly:
        raise HTTPException(404, detail=f"No hay precio para hora {current_hour}")
    
    current_price = hourly[current_hour]
    prices = list(hourly.values())
    stats = calculate_stats(prices)
    
    return {
        "timestamp": datetime.now().isoformat(),
        "date": data["date"].isoformat(),
        "zone": data["zone"],
        "hour": f"{current_hour:02d}:00-{(current_hour+1)%24:02d}:00",
        "price_kwh": current_price,
        "unit": "€/kWh",
        "is_cheap": current_price <= stats["avg"],
        "is_lowest": current_price == stats["min"],
        "is_highest": current_price == stats["max"],
        "avg_day": stats["avg"],
        "source": "ESIOS REE directo"
    }

@app.get("/today")
def get_today_prices(zone: str = "pcb"):
    """Obtiene todos los precios del día de hoy"""
    today = date.today()
    data = fetch_esios_pvpc(today, zone)
    
    hourly = data["hourly"]
    prices = list(hourly.values())
    stats = calculate_stats(prices)
    
    hourly_list = [
        {
            "hour": f"{h:02d}:00-{(h+1)%24:02d}:00",
            "price": hourly[h]
        }
        for h in sorted(hourly.keys())
    ]
    
    return {
        "date": data["date"].isoformat(),
        "zone": data["zone"],
        "hourly_prices": hourly_list,
        "statistics": stats,
        "total_hours": len(hourly_list),
        "source": "ESIOS REE directo"
    }

@app.get("/forecast")
def get_forecast(zone: str = "pcb"):
    """Predicción simple próximas 6 horas basada en media móvil"""
    today_data = get_today_prices(zone)
    prices = [h["price"] for h in today_data["hourly_prices"]]
    
    current_hour = datetime.now().hour
    
    if len(prices) >= 6:
        recent_avg = round(mean(prices[-6:]), 5)
    else:
        recent_avg = round(mean(prices), 5)
    
    forecast = []
    for i in range(1, 7):
        forecast_hour = (current_hour + i) % 24
        forecast.append({
            "hour": f"{forecast_hour:02d}:00-{(forecast_hour+1)%24:02d}:00",
            "predicted_price": recent_avg,
            "confidence": "low",
            "note": "Predicción basada en media móvil 6h"
        })
    
    return {
        "zone": zone,
        "forecast_from": datetime.now().isoformat(),
        "method": "Moving average 6h",
        "predictions": forecast,
        "disclaimer": "Predicción simple, no garantizada"
    }

@app.get("/stats")
def get_statistics(zone: str = "pcb"):
    """Estadísticas completas del día actual"""
    today_data = get_today_prices(zone)
    
    hourly = today_data["hourly_prices"]
    sorted_hours = sorted(hourly, key=lambda x: x["price"])
    
    cheapest_5 = sorted_hours[:5]
    expensive_5 = sorted_hours[-5:][::-1]
    
    return {
        "date": today_data["date"],
        "zone": today_data["zone"],
        "statistics": today_data["statistics"],
        "cheapest_hours": cheapest_5,
        "most_expensive_hours": expensive_5,
        "recommendation": "Programa consumos en horas baratas"
    }

@app.get("/cheapest")
def get_cheapest_hours(zone: str = "pcb", limit: int = 5):
    """N horas más baratas del día para programar consumos"""
    if limit < 1 or limit > 24:
        raise HTTPException(400, detail="limit debe estar entre 1 y 24")
    
    today_data = get_today_prices(zone)
    sorted_hours = sorted(today_data["hourly_prices"], key=lambda x: x["price"])
    
    return {
        "date": today_data["date"],
        "zone": today_data["zone"],
        "cheapest_hours": sorted_hours[:limit],
        "avg_price_day": today_data["statistics"]["avg"]
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
