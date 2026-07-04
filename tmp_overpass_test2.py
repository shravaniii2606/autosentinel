
import requests
for q in [
    '[out:json][timeout:60];node["aeroway"="aerodrome"](19.35,72.78,19.37,72.80);out geom;',
    '[out:json][timeout:60];(node["aeroway"="aerodrome"](19.35,72.78,19.37,72.80);way["aeroway"="aerodrome"](19.35,72.78,19.37,72.80);relation["aeroway"="aerodrome"](19.35,72.78,19.37,72.80));out geom;',
    '[out:json][timeout:60];(node["aeroway"="aerodrome"](19.35,72.78,19.37,72.80);way["aeroway"="aerodrome"](19.35,72.78,19.37,72.80);relation["aeroway"="aerodrome"](19.35,72.78,19.37,72.80));out body geom;'
]:
    print('---')
    print(q)
    r = requests.post('https://overpass-api.de/api/interpreter', data={'data': q}, headers={'User-Agent':'AutoSentinel/1.0','Accept':'application/json'}, timeout=120)
    print(r.status_code, r.text[:200])
