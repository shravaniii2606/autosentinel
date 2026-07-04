
from pathlib import Path
import subprocess
exe = r'c:\Users\Admin\autosentinel\backend\venv\Scripts\python.exe'
script = r'c:\Users\Admin\autosentinel\notebooks\fetch_osm_layers.py'
proc = subprocess.run([exe, script, '--output-dir', r'c:\Users\Admin\autosentinel\data', '--bbox', '19.35','72.78','19.37','72.80'], capture_output=True, text=True)
print('rc', proc.returncode)
print('stdout:', proc.stdout)
print('stderr:', proc.stderr)
for name in ['osm_airports.geojson','osm_railways.geojson','osm_rivers.geojson','osm_industrial.geojson','osm_protected.geojson']:
    p = Path(r'c:\Users\Admin\autosentinel\data') / name
    print(name, p.exists(), p.stat().st_size if p.exists() else None)
