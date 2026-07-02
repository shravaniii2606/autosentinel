import pandas as pd
import requests
import gzip
import io

df = pd.read_csv('https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv')
india = df[df['Location'] == 'India']
url = india.iloc[0]['Url']
print('Checking:', url)
r = requests.get(url, timeout=60)
with gzip.open(io.BytesIO(r.content), 'rt') as f:
    for i, line in enumerate(f):
        if i < 3:
            print('Line', i, ':', line[:300])
        else:
            break