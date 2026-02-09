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

# URL base de la API gratuita de precios (usa datos oficiales REE)
BASE_URL = "https://api.preciodelaluz.org/v1/prices"

async def fetch_pvpc_data(zone: str = "PCB") -> Dict:
    """Obtiene datos reales de PVPC desde API gratuita"""
    try:
        url = f"{BASE_URL}/now?zone={zone}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Error obteniendo datos REE: {str(e)}")

def calculate_statistics(prices: List[float]) -> Dict:
    """Calcula estadísticas de precios"""
    if not prices:
        return {"min": 0, "max": 0, "avg": 0}
    return {
        "min": round(min(prices), 4),
        "max": round(max(prices), 4),
        "avg": round(mean(prices), 4)
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
async def get_today_prices(zone: str = "PCB"):
    """Obtiene todos los precios del día de hoy"""
    try:
        url = f"https://api.preciodelaluz.org/v1/prices/all?zone={zone}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
        
        # Extraer precios por hora
        hourly_prices = []
        for hour, info in data.items():
            if hour not in ["date", "units"]:
                try:
                    hourly_prices.append({
                        "hour": hour,
                        "price": float(info.get("price", 0)) / 1000,  # Convertir a €/kWh
                        "is_cheap": info.get("is-cheap", False),
                        "is_under_avg": info.get("is-under-avg", False)
                    })
                except (ValueError, TypeError):
                    continue
        
        prices = [h["price"] for h in hourly_prices]
        stats = calculate_statistics(prices)
        
        return {
            "date": data.get("date", datetime.now().strftime("%Y-%m-%d")),
            "zone": zone,
            "hourly_prices": sorted(hourly_prices, key=lambda x: x["hour"]),
            "statistics": stats,
            "total_hours": len(hourly_prices),
            "source": "REE oficial"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Error: {str(e)}")

@app.get("/forecast")
async def get_forecast(zone: str = "PCB"):
    """Predicción simple próximas 6 horas basada en media móvil"""
    today_data = await get_today_prices(zone)
    prices = [h["price"] for h in today_data["hourly_prices"]]
    
    current_hour = datetime.now().hour
    
    # Predicción naive: promedio últimas 6 horas
    if len(prices) >= 6:
        recent_avg = round(mean(prices[-6:]), 4)
    else:
        recent_avg = round(mean(prices), 4)
    
    forecast = []
    for i in range(1, 7):
        forecast_hour = (current_hour + i) % 24
        forecast.append({
            "hour": f"{forecast_hour:02d}:00-{forecast_hour+1:02d}:00",
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
