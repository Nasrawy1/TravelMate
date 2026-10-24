"""Builds verified city records (Google Freebase city ID, center, time zone) for well-known cities. No API quota."""
import json, re, requests, airportsdata

# label: (country_code, airports, aliases)
NEW = {
    "Abu Dhabi": ("ae", ["AUH"], []), "Sharjah": ("ae", ["SHJ"], []), "Muscat": ("om", ["MCT"], []),
    "Kuwait City": ("kw", ["KWI"], ["kuwait"]), "Manama": ("bh", ["BAH"], ["bahrain"]),
    "Medina": ("sa", ["MED"], ["madinah", "al madinah"]), "Dammam": ("sa", ["DMM"], []),
    "Beirut": ("lb", ["BEY"], []), "Basra": ("iq", ["BSR"], ["basrah"]),
    "Sulaymaniyah": ("iq", ["ISU"], ["sulaimani", "slemani"]), "Najaf": ("iq", ["NJF"], []),
    "Casablanca": ("ma", ["CMN"], []), "Marrakesh": ("ma", ["RAK"], ["marrakech"]), "Tunis": ("tn", ["TUN"], []),
    "Algiers": ("dz", ["ALG"], []), "Alexandria": ("eg", ["HBE"], []),
    "Sharm El Sheikh": ("eg", ["SSH"], ["sharm el-sheikh", "sharm"]), "Hurghada": ("eg", ["HRG"], []),
    "Antalya": ("tr", ["AYT"], []), "Izmir": ("tr", ["ADB"], []), "Ankara": ("tr", ["ESB"], []),
    "Trabzon": ("tr", ["TZX"], []), "Baku": ("az", ["GYD"], []), "Tbilisi": ("ge", ["TBS"], []),
    "Tashkent": ("uz", ["TAS"], []),
    "Berlin": ("de", ["BER"], []), "Munich": ("de", ["MUC"], ["munchen", "münchen"]), "Frankfurt": ("de", ["FRA"], []),
    "Vienna": ("at", ["VIE"], ["wien"]), "Amsterdam": ("nl", ["AMS"], []), "Brussels": ("be", ["BRU"], []),
    "Madrid": ("es", ["MAD"], []), "Barcelona": ("es", ["BCN"], []), "Lisbon": ("pt", ["LIS"], ["lisboa"]),
    "Milan": ("it", ["MXP", "LIN"], ["milano"]), "Athens": ("gr", ["ATH"], []), "Prague": ("cz", ["PRG"], []),
    "Budapest": ("hu", ["BUD"], []), "Zurich": ("ch", ["ZRH"], ["zürich"]), "Geneva": ("ch", ["GVA"], []),
    "Copenhagen": ("dk", ["CPH"], []), "Stockholm": ("se", ["ARN", "BMA"], []), "Manchester": ("gb", ["MAN"], []),
    "Dublin": ("ie", ["DUB"], []), "Sarajevo": ("ba", ["SJJ"], []), "Warsaw": ("pl", ["WAW"], []),
    "Bangkok": ("th", ["BKK", "DMK"], []), "Phuket": ("th", ["HKT"], []), "Kuala Lumpur": ("my", ["KUL"], []),
    "Singapore": ("sg", ["SIN"], []), "Jakarta": ("id", ["CGK"], []), "Tokyo": ("jp", ["HND", "NRT"], []),
    "Seoul": ("kr", ["ICN", "GMP"], []), "Beijing": ("cn", ["PEK", "PKX"], []), "Shanghai": ("cn", ["PVG", "SHA"], []),
    "Hong Kong": ("hk", ["HKG"], []), "Male": ("mv", ["MLE"], ["malé"]), "Delhi": ("in", ["DEL"], ["new delhi"]),
    "Mumbai": ("in", ["BOM"], []), "Karachi": ("pk", ["KHI"], []), "Lahore": ("pk", ["LHE"], []),
    "Islamabad": ("pk", ["ISB"], []),
    "New York": ("us", ["JFK", "LGA", "EWR"], ["new york city", "nyc"]), "Los Angeles": ("us", ["LAX"], []),
    "Miami": ("us", ["MIA"], []), "Toronto": ("ca", ["YYZ", "YTZ"], []),
    "Nairobi": ("ke", ["NBO"], []), "Cape Town": ("za", ["CPT"], []),
}
UA = {"User-Agent": "TravelMate-graduation-project/1.0 (city table build)"}

def sparql(query):
    r = requests.get("https://query.wikidata.org/sparql", params={"query": query, "format": "json"}, headers=UA, timeout=90)
    r.raise_for_status()
    return r.json()["results"]["bindings"]

def norm(text):
    return re.sub(r"[^a-z]", "", text.lower().replace("é", "e").replace("ü", "u"))

def city_rows(query_values, by_airport):
    out = []
    size = 20 if by_airport else 3
    for chunk in range(0, len(query_values), size):
        vals = " ".join(query_values[chunk:chunk + size])
        if by_airport:
            q = f"""SELECT ?key ?city ?cityLabel ?mid ?coord ?pop WHERE {{ VALUES ?key {{ {vals} }}
              ?a wdt:P238 ?key; wdt:P931 ?city. ?city wdt:P646 ?mid; wdt:P625 ?coord. OPTIONAL {{ ?city wdt:P1082 ?pop }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }}"""
        else:
            q = f"""SELECT ?key ?cc ?city ?cityLabel ?mid ?coord ?pop WHERE {{ VALUES (?key ?cc) {{ {vals} }}
              ?country wdt:P297 ?cc. ?city rdfs:label ?key; wdt:P17 ?country; wdt:P646 ?mid; wdt:P625 ?coord.
              OPTIONAL {{ ?city wdt:P1082 ?pop }} SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }}"""
        out += sparql(q)
    return out

def record(b):
    lon, lat = map(float, re.findall(r"-?\d+\.?\d*", b["coord"]["value"])[:2])
    return {"mid": b["mid"]["value"], "center": (round(lat, 4), round(lon, 4)),
            "pop": float(b.get("pop", {}).get("value", 0) or 0), "qid": b["city"]["value"].rsplit("/", 1)[1],
            "wd_label": b["cityLabel"]["value"]}

names = {label: {norm(label)} | {norm(a) for a in aliases} for label, (_, _, aliases) in NEW.items()}
airport_owner = {a: label for label, (_, airports, _) in NEW.items() for a in airports}
via_airport = {}
for b in city_rows([f'"{a}"' for a in airport_owner], True):
    label = airport_owner[b["key"]["value"]]
    if norm(b["cityLabel"]["value"]) in names[label]:
        rec = record(b)
        if label not in via_airport or rec["pop"] > via_airport[label]["pop"]:
            via_airport[label] = rec
via_label = {}
missing = [label for label in NEW if label not in via_airport]
print("not matched through an airport:", missing)
for b in city_rows([f'("{label}"@en "{NEW[label][0].upper()}")' for label in missing], False):
    label, rec = b["key"]["value"], record(b)
    if label not in via_label or rec["pop"] > via_label[label]["pop"]:
        via_label[label] = rec
by_label = {}
for label in NEW:
    a, l = via_airport.get(label), via_label.get(label)
    by_label[label] = a or l
    if by_label[label]:
        by_label[label]["source"] = "airport_serves_city" if a else "label_country_largest"
        by_label[label]["agree"] = (a["mid"] == l["mid"]) if a and l else None
served = {}
airports_db = airportsdata.load("IATA")
out, problems = {}, []
for label, (cc, airports, aliases) in NEW.items():
    city = by_label.get(label)
    zones = {airports_db[a]["tz"] for a in airports if a in airports_db}
    missing = [a for a in airports if a not in airports_db or airports_db[a]["country"].lower() != cc]
    if not city:
        problems.append(f"{label}: no Wikidata city match"); continue
    if missing or len(zones) != 1:
        problems.append(f"{label}: airport check failed {missing} {zones}"); continue
    serves = city["source"]
    out[label] = {"country_code": cc, "airports": airports, "timezone": zones.pop(), "center": city["center"],
                  "aliases": aliases, "google_city_id": city["mid"], "wikidata": city["qid"], "source": serves, "agree": city["agree"], "wd_label": city["wd_label"],
                  "airport_names": {a: f"{airports_db[a]['name']} ({airports_db[a]['city']})" for a in airports}}
json.dump({"cities": out, "problems": problems}, open("new_cities.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(out), "cities built;", "problems:", problems)
for label, c in out.items():
    print(f"{label:16} {c['google_city_id']:12} {c['timezone']:20} {c['center']} {c['source']} agree={c['agree']} wd={c['wd_label']} {c['airport_names']}")
