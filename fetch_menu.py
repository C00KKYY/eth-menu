#!/usr/bin/env python3
"""Holt den ETH-Wochenplan und speichert Rohdaten + Tagesmenues mehrerer Mensen.
Schreibt data/tage/<YYYY-MM-DD>.json fuer heute und die naechsten TAGE_VORAUS Tage,
damit ein verspaeteter GitHub-Lauf trotzdem die Datei fuer morgen bereitstellt.
Nur Standardbibliothek. Env: FACILITY_IDS (kommagetrennt, Default siehe unten).
Endpunkt und Feldnamen am 2026-11-09 gegen die Live-API geprueft."""
import glob, json, os, sys, time, urllib.error, urllib.request, urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Hoenggerberg. IDs/Namen aus .../v1/facilities
NAMES = {19: "food market (HPR)", 20: "FUSION meal (HCI)",
         14: "Alumni quattro Lounge (HIL)", 22: "Rice Up! (HIT)"}
FACILITY_IDS = [int(x) for x in os.environ.get("FACILITY_IDS", "19,20,14,22").split(",")]
TAGE_VORAUS = 14

today = datetime.now(ZoneInfo("Europe/Zurich")).date()
iso = today.isoformat()
params = urllib.parse.urlencode({
    "client-id": "ethz-wcms", "lang": "de",
    "rs-first": 0, "rs-size": 500, "valid-after": iso,
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


def meals_for(fid, tag):
    # Pro Facility kommen mehrere Wochenplaene (aktuelle + kommende Wochen).
    # Nur den Plan nehmen, der heute gilt. None = kein gueltiger Plan.
    rotas = [r for r in raw.get("weekly-rota-array", [])
             if r.get("facility-id") == fid
             and r.get("valid-from", "") <= tag.isoformat() <= r.get("valid-to", "9999-12-31")]
    if not rotas:
        return None
    meals = []
    for rota in rotas:
        for day in rota.get("day-of-week-array", []):
            if day.get("day-of-week-code") != tag.isoweekday():
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


def tagesplan(tag):
    mensen = []
    for fid in FACILITY_IDS:
        meals = meals_for(fid, tag)
        status = "unbekannt" if meals is None else ("offen" if meals else "geschlossen")
        mensen.append({"facility_id": fid, "name": NAMES.get(fid, str(fid)),
                       "status": status, "offen": status == "offen", "menues": meals or []})
    return {"datum": tag.isoformat(), "erzeugt": iso, "mensen": mensen}


os.makedirs("data/tage", exist_ok=True)
for i in range(TAGE_VORAUS + 1):
    tag = today + timedelta(days=i)
    plan = tagesplan(tag)
    with open(f"data/tage/{tag.isoformat()}.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)
    if i == 0:
        with open("data/menu-heute.json", "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=1)
    print(tag.isoformat(), ", ".join(f"{m['name']}: {len(m['menues'])}" for m in plan["mensen"]))

# Tagesdateien aelter als 7 Tage entfernen
grenze = (today - timedelta(days=7)).isoformat()
for p in glob.glob("data/tage/*.json"):
    if os.path.basename(p)[:10] < grenze:
        os.remove(p)
