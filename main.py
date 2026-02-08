from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import uvicorn
from datetime import datetime
from typing import Dict, List, Optional
from statistics import mean

app = FastAPI(
    title="⚡ Spain Energy PVPC API PRO",
    description="API real de precios PVPC España con datos actualizados de REE",
    version="3.0.0"
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
        "api": "⚡ Spain Energy PVPC API PRO",
        "version": "3.0.0",
        "status": "✅ LIVE",
        "data_source": "REE oficial vía preciodelaluz.org",
        "endpoints": [
            "/now - Precio actual PVPC",
            "/today - Precios completos hoy",
            "/forecast - Predicción próximas 6h",
            "/stats - Estadísticas diarias",
            "/cheapest - 5 horas más baratas hoy"
        ],
        "zones": ["PCB (Península/Canarias/Baleares)", "CYM (Ceuta y Melilla)"],
        "docs": "/docs"
    }

@app.get("/now")
async def get_current_price(zone: str = "PCB"):
    """Obtiene el precio actual de la luz en tiempo real"""
    data = await fetch_pvpc_data(zone)
    
    return {
        "timestamp": datetime.now().isoformat(),
        "zone": zone,
        "current_price_kwh": data.get("price", "N/A"),
        "unit": "€/kWh",
        "hour": data.get("hour", "N/A"),
        "is_cheap": data.get("is-cheap", False),
        "is_under_avg": data.get("is-under-avg", False),
        "market": data.get("market", "N/A"),
        "source": "REE oficial"
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
async def get_statistics(zone: str = "PCB"):
    """Estadísticas completas del día"""
    today = await get_today_prices(zone)
    
    hourly = today["hourly_prices"]
    prices = [h["price"] for h in hourly]
    
    cheap_hours = [h for h in hourly if h["is_cheap"]]
    expensive_hours = sorted(hourly, key=lambda x: x["price"], reverse=True)[:5]
    
    return {
        "date": today["date"],
        "zone": zone,
        "statistics": today["statistics"],
        "cheap_hours_count": len(cheap_hours),
        "top_5_expensive": expensive_hours,
        "recommendation": "Consume entre 00h-08h para ahorrar" if cheap_hours else "Precios elevados hoy",
        "avg_price_comparison": {
            "today": today["statistics"]["avg"],
            "threshold_cheap": 0.10,
            "threshold_expensive": 0.15
        }
    }

@app.get("/cheapest")
async def get_cheapest_hours(zone: str = "PCB", limit: int = 5):
    """Obtiene las N horas más baratas del día"""
    today = await get_today_prices(zone)
    
    sorted_hours = sorted(today["hourly_prices"], key=lambda x: x["price"])
    cheapest = sorted_hours[:limit]
    
    return {
        "date": today["date"],
        "zone": zone,
        "cheapest_hours": cheapest,
        "recommendation": f"Programa consumos intensivos en: {', '.join([h['hour'] for h in cheapest])}",
        "potential_savings": f"{round((today['statistics']['max'] - today['statistics']['min']) * 100, 2)}% vs hora más cara"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
