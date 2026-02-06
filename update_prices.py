import requests
import json
import schedule
import time

def fetch_ree_prices():
    # REE API real
    r = requests.get("https://www.ree.es/es/datos/peninsulas/precios-especificos-del-mercado")
    data = r.json()
    with open("prices.json", "w") as f:
        json.dump(data, f)
    print("💡 Precios actualizados:", data["hoy"])

schedule.every().hour.do(fetch_ree_prices)
while True:
    schedule.run_pending()
    time.sleep(60)
