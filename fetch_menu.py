#!/usr/bin/env python3
"""Holt den ETH-Wochenplan und speichert Rohdaten + Tagesmenues mehrerer Mensen.
Nur Standardbibliothek. Env: FACILITY_IDS (kommagetrennt, Default siehe unten).
Endpunkt und Feldnamen am 2026-11-09 gegen die Live-API geprueft."""
import json, os, sys, time, urllib.error, urllib.request, urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

# Hoenggerberg. IDs/Namen aus .../v1/facilities
NAMES = {19: "food market (HPR)", 20: "FUSION meal (HCI)",
         14: "Alumni quattro Lounge (HIL)", 22: "Rice Up! (HIT)"}
FACILITY_IDS = [int(x) for x in os.environ.get("FACILITY_IDS", "19,20,14,22").split(",")]

today = datetime.now(ZoneInfo("Europe/Zurich")).date()
iso = today.isoformat()
params = urllib.parse.urlencode({
    "client-id": "ethz-wcms", "lang": "de",
    "rs-first": 0, "rs-size": 100, "valid-after": iso,
})
url = f"https://idapps.ethz.ch/cookpit-pub-services/v1/weeklyrotas?{params}"
req = urllib.request.Request(url, headers={"User-Agent": "eth-menu-sync", "Accept": "application/json"})

# Die API liefert sporadisch 502: bis zu 5 Versuche.
for attempt in range(5):
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = json.load(r)
        break
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"Versuch {attempt + 1} fehlgeschlagen: {e}")
        if attempt == 4:
            raise
        time.sleep(5 * (attempt + 1))

os.makedirs("data", exist_ok=True)
with open("data/raw.json", "w", encoding="utf-8") as f:
    json.dump(raw, f, ensure_ascii=False, indent=1)


def clean(s):
    return s.strip() if isinstance(s, str) else s


def meals_for(fid):
    # Pro Facility kommen mehrere Wochenplaene (aktuelle + kommende Wochen).
    # Nur den Plan nehmen, der heute gilt. None = kein gueltiger Plan.
    rotas = [r for r in raw.get("weekly-rota-array", [])
             if r.get("facility-id") == fid
             and r.get("valid-from", "") <= iso <= r.get("valid-to", "9999-12-31")]
    if not rotas:
        return None
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
                            "zeit": clean(mt.get("name")), "linie": clean(line.get("name")),
                            "menue": clean(m.get("name")), "beschreibung": clean(m.get("description")),
                            "klasse": [c.get("desc") for c in m.get("meal-class-array", [])],
                            "preise": [{"gruppe": p.get("customer-group-desc"), "preis": p.get("price")}
                                       for p in m.get("meal-price-array", [])],
                        })
    return meals


mensen = []
for fid in FACILITY_IDS:
    meals = meals_for(fid)
    mensen.append({"facility_id": fid, "name": NAMES.get(fid, str(fid)),
                   "offen": bool(meals), "menues": meals or []})
    print(f"{NAMES.get(fid, fid)}: " + ("kein Wochenplan" if meals is None else f"{len(meals)} Menues"))

with open("data/menu-heute.json", "w", encoding="utf-8") as f:
    json.dump({"datum": iso, "mensen": mensen}, f, ensure_ascii=False, indent=1)

if not any(m["menues"] for m in mensen):
    print("Hinweis: heute in keiner Mensa Menues publiziert (geschlossen?)")
