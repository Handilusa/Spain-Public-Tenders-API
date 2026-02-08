from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, date
from statistics import mean
import uvicorn
import pvpc  # librería wrapper de ESIOS

app = FastAPI(
    title="⚡ Spain PVPC Energy API (ESIOS)",
    description="Precios PVPC reales por hora (€/kWh) para España usando el API de REE (ESIOS) vía librería pvpc",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def _get_zone_hours(day: date, zone: str):
    """
    Devuelve (fecha, lista de horas [{hour, price}], stats) para la zona dada.
    zone: 'pcb' (Península/Canarias/Baleares) o 'cm' (Ceuta/Melilla)
    """
    try:
        r = pvpc.get_pvpc_day(day)
    except pvpc.PVPCNoDataForDay:
        raise HTTPException(
            status_code=503,
            detail="Aún no hay datos PVPC publicados para este día en ESIOS",
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Error PVPC: {repr(e)}")

    z = zone.lower()
    if z == "pcb":
        hours_dict = r.data.pcb.hours
        zone_name = "PCB"
    elif z in ("cm", "cym"):
        hours_dict = r.data.cm.hours
        zone_name = "CM"
    else:
        raise HTTPException(
            status_code=400,
            detail="Parámetro 'zone' debe ser 'pcb' o 'cm'",
        )

    hourly = []
    for h_str, price in hours_dict.items():
        h = int(h_str)
        hourly.append(
            {
                "hour": f"{h:02d}:00-{(h+1)%24:02d}:00",
                "price": float(price),  # €/kWh directamente
            }
        )
    hourly_sorted = sorted(hourly, key=lambda x: x["hour"])
    prices = [h["price"] for h in hourly_sorted]
    stats = {
        "min": round(min(prices), 5),
        "max": round(max(prices), 5),
        "avg": round(mean(prices), 5),
    }

    return r.day, zone_name, hourly_sorted, stats

@app.get("/")
def root():
    return {
        "api": "⚡ Spain PVPC Energy API (ESIOS)",
        "version": "1.0.0",
        "status": "✅ LIVE",
        "source": "ESIOS (REE) vía librería pvpc",
        "endpoints": [
            "/now - Precio actual",
            "/today - Precios de hoy",
            "/stats - Estadísticas del día",
            "/cheapest - Horas más baratas de hoy",
            "/forecast - Predicción simple 6h (media móvil)",
        ],
        "zones": ["pcb (Península/Canarias/Baleares)", "cm (Ceuta/Melilla)"],
        "docs": "/docs",
    }

@app.get("/today")
def today(zone: str = "pcb"):
    """Todos los precios del día actual (24h) + estadísticas"""
    today_date = date.today()
    day, zone_name, hourly, stats = _get_zone_hours(today_date, zone)

    return {
        "date": day.isoformat(),
        "zone": zone_name,
        "hourly_prices": hourly,
        "statistics": stats,
        "total_hours": len(hourly),
        "source": "ESIOS (REE) vía pvpc",
    }

@app.get("/now")
def now(zone: str = "pcb"):
    """Precio actual (hora en curso) + flags de barato/caro respecto al día"""
    today_date = date.today()
    day, zone_name, hourly, stats = _get_zone_hours(today_date, zone)
    current_hour = datetime.now().hour
    current_range = f"{current_hour:02d}:00-{(current_hour+1)%24:02d}:00"

    current_entry = next(
        (h for h in hourly if h["hour"].startswith(f"{current_hour:02d}:")), None
    )
    if not current_entry:
        raise HTTPException(status_code=404, detail="No hay dato para esta hora")

    price = current_entry["price"]
    is_cheap = price <= stats["avg"]
    is_lowest = price == stats["min"]
    is_highest = price == stats["max"]

    return {
        "timestamp": datetime.now().isoformat(),
        "date": day.isoformat(),
        "zone": zone_name,
        "hour_range": current_range,
        "price_kwh": price,
        "unit": "€/kWh",
        "is_cheap_vs_avg": is_cheap,
        "is_lowest_day": is_lowest,
        "is_highest_day": is_highest,
        "avg_price_day": stats["avg"],
        "source": "ESIOS (REE) vía pvpc",
    }

@app.get("/stats")
def stats(zone: str = "pcb"):
    """Estadísticas completas del día actual"""
    today_date = date.today()
    day, zone_name, hourly, stats = _get_zone_hours(today_date, zone)
    sorted_hours = sorted(hourly, key=lambda x: x["price"])
    cheapest = sorted_hours[:5]
    expensive = sorted_hours[-5:][::-1]

    return {
        "date": day.isoformat(),
        "zone": zone_name,
        "statistics": stats,
        "cheapest_hours": cheapest,
        "most_expensive_hours": expensive,
        "recommendation": "Programa consumos intensivos en las horas más baratas",
    }

@app.get("/cheapest")
def cheapest(limit: int = 5, zone: str = "pcb"):
    """N horas más baratas de hoy"""
    if limit <= 0 or limit > 24:
        raise HTTPException(status_code=400, detail="limit debe estar entre 1 y 24")

    today_date = date.today()
    day, zone_name, hourly, stats = _get_zone_hours(today_date, zone)
    sorted_hours = sorted(hourly, key=lambda x: x["price"])
    cheapest_hours = sorted_hours[:limit]

    return {
        "date": day.isoformat(),
        "zone": zone_name,
        "cheapest_hours": cheapest_hours,
        "avg_price_day": stats["avg"],
    }

@app.get("/forecast")
def forecast(zone: str = "pcb"):
    """Predicción naive próximas 6h usando media de las últimas 6 horas disponibles"""
    today_date = date.today()
    day, zone_name, hourly, stats = _get_zone_hours(today_date, zone)
    prices = [h["price"] for h in hourly]
    if len(prices) >= 6:
        base = round(mean(prices[-6:]), 5)
    else:
        base = stats["avg"]

    current_hour = datetime.now().hour
    predictions = []
    for i in range(1, 7):
        h = (current_hour + i) % 24
        predictions.append(
            {
                "hour": f"{h:02d}:00-{(h+1)%24:02d}:00",
                "predicted_price": base,
                "unit": "€/kWh",
                "method": "6h moving average",
            }
        )

    return {
        "date": day.isoformat(),
        "zone": zone_name,
        "from_hour": current_hour,
        "predictions": predictions,
        "note": "Predicción simple basada en media móvil, sin garantías",
    }

if __name__ == "__main__":
    # Para pruebas locales
    uvicorn.run(app, host="0.0.0.0", port=8000)
