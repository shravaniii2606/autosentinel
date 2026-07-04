
import requests
queries = [
    '[out:json][timeout:60];(node["aeroway"="aerodrome"](19.35,72.78,19.37,72.80);way["aeroway"="aerodrome"](19.35,72.78,19.37,72.80););out geom;',
    '[out:json][timeout:60];(node["aeroway"="aerodrome"](19.35,72.78,19.37,72.80);way["aeroway"="aerodrome"](19.35,72.78,19.37,72.80));out geom;',
    '[out:json][timeout:60];(way["railway"](19.35,72.78,19.37,72.80););out geom;'
]
for q in queries:
    print('---')
    print(q)
    r = requests.post('https://overpass-api.de/api/interpreter', data={'data': q}, headers={'User-Agent':'AutoSentinel/1.0','Accept':'application/json'}, timeout=120)
    print('status', r.status_code)
    print('text', r.text[:400])
