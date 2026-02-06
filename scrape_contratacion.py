import requests
from bs4 import BeautifulSoup
import json

@app.get("/licitaciones/reales")
def tenders_reales():
    url = "https://contrataciondelestado.es/wps/poc?Pagina=1"
    r = requests.get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    
    tenders = []
    for row in soup.select("table tr")[:10]:
        title = row.select_one("td.title").text
        budget = row.select_one("td.importe").text  
        tenders.append({"title": title, "budget": budget})
    
    return {"reales": tenders, "total_paginas": 4500}
