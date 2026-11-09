#!/usr/bin/env python3
"""Holt den ETH-Wochenplan und speichert Rohdaten + Tagesmenue.
Nur Standardbibliothek. Env: FACILITY_ID (Default 19 = food market, HPR Hoenggerberg).
Endpunkt und Feldnamen am 2026-11-09 gegen die Live-API geprueft."""
import json, os, sys, urllib.request, urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

FACILITY_ID = int(os.environ.get("FACILITY_ID", "19"))
today = datetime.now(ZoneInfo("Europe/Zurich")).date()
params = urllib.parse.urlencode({
    "client-id": "ethz-wcms", "lang": "de",
    "rs-first": 0, "rs-size": 100, "valid-after": today.isoformat(),
})
url = f"https://idapps.ethz.ch/cookpit-pub-services/v1/weeklyrotas?{params}"
req = urllib.request.Request(url, headers={"User-Agent": "eth-menu-sync", "Accept": "application/json"})
with urllib.request.urlopen(req, timeout=30) as r:
    raw = json.load(r)

os.makedirs("data", exist_ok=True)
with open("data/raw.json", "w", encoding="utf-8") as f:
    json.dump(raw, f, ensure_ascii=False, indent=1)

# Pro Facility kommen mehrere Wochenplaene (aktuelle + kommende Wochen) zurueck.
# Nur den Plan nehmen, der heute gilt, sonst landen Menues anderer Wochen im Ergebnis.
iso = today.isoformat()
rotas = [r for r in raw.get("weekly-rota-array", [])
         if r.get("facility-id") == FACILITY_ID
         and r.get("valid-from", "") <= iso <= r.get("valid-to", "9999-12-31")]
if not rotas:
    sys.exit(f"Kein gueltiger Wochenplan fuer Facility {FACILITY_ID} am {iso}: data/raw.json pruefen")

meals = []
for rota in rotas:
    for day in rota.get("day-of-week-array", []):
        if day.get("day-of-week-code") != today.isoweekday():
            continue
        for oh in day.get("opening-hour-array", []):
            for mt in oh.get("meal-time-array", []):
                for line in mt.get("line-array", []):
                    m = line.get("meal")
                    if not m:
                        continue
                    meals.append({
                        "zeit": mt.get("name"), "linie": line.get("name"),
                        "menue": m.get("name"), "beschreibung": m.get("description"),
                        "klasse": [c.get("desc") for c in m.get("meal-class-array", [])],
                        "preise": [{"gruppe": p.get("customer-group-desc"), "preis": p.get("price")}
                                   for p in m.get("meal-price-array", [])],
                    })

with open("data/menu-heute.json", "w", encoding="utf-8") as f:
    json.dump({"datum": iso, "facility_id": FACILITY_ID, "menues": meals},
              f, ensure_ascii=False, indent=1)
print(f"{len(meals)} Menues gefunden fuer {iso}")
if not meals:
    # Wochenplan existiert, aber heute keine Linien (Feiertag/geschlossen): kein Fehler.
    print("Hinweis: heute keine Menues publiziert (geschlossen?)")
