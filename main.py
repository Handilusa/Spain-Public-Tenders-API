from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
import uvicorn
from datetime import datetime, date
from statistics import mean
from typing import Dict, List

app = FastAPI(
    title="⚡ Spain Energy PVPC API",
    description="API real de precios PVPC España con datos REE",
    version="5.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def fetch_pvpc_today(zone: str) -> Dict:
    """Obtiene precios PVPC del día desde endpoint público REE"""
    # API pública de REE (archives) - sin token necesario
    today_str = date.today().strftime("%Y-%m-%d")
    
    # URLs públicas de archivos JSON de REE
    # PCB: Península/Canarias/Baleares, CYM: Ceuta/Melilla
    if zone.lower() == "pcb":
        url = f"https://api.esios.ree.es/archives/70/download_json?locale=es&date={today_str}"
    else:  # cm / cym
        url = f"https://api.esios.ree.es/archives/71/download_json?locale=es&date={today_str}"
    
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        hourly = {}
        for entry in data.get("PVPC", []):
            hour_str = entry.get("Hora", "")
            if not hour_str or "-" not in hour_str:
                continue
            
            hour = int(hour_str.split("-")[0]) - 1  # "01-02" → hora 0
            price_str = entry.get("PCB" if zone.lower() == "pcb" else "CYM", "0")
            
            # Formato: "123,45" → 123.45 (€/MWh) → 0.12345 (€/kWh)
            price_mwh = float(price_str.replace(",", "."))
            price_kwh = round(price_mwh / 1000, 5)
            hourly[hour] = price_kwh
        
        if not hourly:
            raise HTTPException(503, detail="No hay datos PVPC disponibles para hoy")
        
        return {
            "date": date.today(),
            "zone": zone.upper(),
            "hourly": hourly
        }
    
    except requests.RequestException as e:
        raise HTTPException(503, detail=f"Error obteniendo datos REE: {str(e)}")

def calculate_stats(prices: List[float]) -> Dict:
    if not prices:
        return {"min": 0, "max": 0, "avg": 0}
    return {
        "min": round(min(prices), 5),
        "max": round(max(prices), 5),
        "avg": round(mean(prices), 5)
    }

@app.get("/")
def root():
    return {
        "api": "⚡ Spain Energy PVPC API",
        "version": "5.0.0",
        "status": "✅ LIVE",
        "data_source": "REE archives (público, sin token)",
        "endpoints": [
            "/now?zone=pcb - Precio actual",
            "/today?zone=pcb - Precios 24h",
            "/forecast?zone=pcb - Predicción 6h",
            "/stats?zone=pcb - Estadísticas",
            "/cheapest?zone=pcb&limit=5 - Horas baratas"
        ],
        "zones": ["pcb (Península/Canarias/Baleares)", "cm (Ceuta/Melilla)"],
        "docs": "/docs"
    }

@app.get("/now")
def get_current_price(zone: str = "pcb"):
    data = fetch_pvpc_today(zone)
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
        "source": "REE archives"
    }

@app.get("/today")
def get_today_prices(zone: str = "pcb"):
    data = fetch_pvpc_today(zone)
    hourly = data["hourly"]
    prices = list(hourly.values())
    stats = calculate_stats(prices)
    
    hourly_list = [
        {"hour": f"{h:02d}:00-{(h+1)%24:02d}:00", "price": hourly[h]}
        for h in sorted(hourly.keys())
    ]
    
    return {
        "date": data["date"].isoformat(),
        "zone": data["zone"],
        "hourly_prices": hourly_list,
        "statistics": stats,
        "total_hours": len(hourly_list),
        "source": "REE archives"
    }

@app.get("/forecast")
def get_forecast(zone: str = "pcb"):
    today_data = get_today_prices(zone)
    prices = [h["price"] for h in today_data["hourly_prices"]]
    current_hour = datetime.now().hour
    
    recent_avg = round(mean(prices[-6:]) if len(prices) >= 6 else mean(prices), 5)
    
    forecast = [
        {
            "hour": f"{(current_hour+i)%24:02d}:00-{(current_hour+i+1)%24:02d}:00",
            "predicted_price": recent_avg,
            "confidence": "low",
            "note": "Media móvil 6h"
        }
        for i in range(1, 7)
    ]
    
    return {
        "zone": zone,
        "forecast_from": datetime.now().isoformat(),
        "method": "Moving average 6h",
        "predictions": forecast
    }

@app.get("/stats")
def get_statistics(zone: str = "pcb"):
    today_data = get_today_prices(zone)
    hourly = today_data["hourly_prices"]
    sorted_hours = sorted(hourly, key=lambda x: x["price"])
    
    return {
        "date": today_data["date"],
        "zone": today_data["zone"],
        "statistics": today_data["statistics"],
        "cheapest_hours": sorted_hours[:5],
        "most_expensive_hours": sorted_hours[-5:][::-1],
        "recommendation": "Programa consumos en horas baratas"
    }

@app.get("/cheapest")
def get_cheapest_hours(zone: str = "pcb", limit: int = 5):
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
