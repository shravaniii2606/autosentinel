
import requests
bbox=(19.35,72.78,19.37,72.80)
query='[out:json][timeout:60];(' + ';'.join([part.format(south=bbox[0], west=bbox[1], north=bbox[2], east=bbox[3]) for part in ['node["aeroway"="aerodrome"]({south},{west},{north},{east})', 'way["aeroway"="aerodrome"]({south},{west},{north},{east})', 'relation["aeroway"="aerodrome"]({south},{west},{north},{east})']]) + ');out geom;'
print(query)
res = requests.post('https://overpass-api.de/api/interpreter', data={'data': query}, headers={'User-Agent':'AutoSentinel/1.0','Accept':'application/json'}, timeout=120)
print('status', res.status_code)
print(res.text[:8000])
