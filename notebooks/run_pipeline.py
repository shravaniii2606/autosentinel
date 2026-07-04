import argparse
import subprocess
import sys
import os
import uuid
import time


def run(cmd, **kwargs):
    print(f"Running: {' '.join(cmd)}")
    subprocess.check_call(cmd, **kwargs)


def main(minx, miny, maxx, maxy, job_dir):
    os.makedirs(job_dir, exist_ok=True)
    tif_path = os.path.join(job_dir, 'change.tif')
    detected_geojson = os.path.join(job_dir, 'new_construction.geojson')
    scored_geojson = os.path.join(job_dir, 'scored_zones.geojson')

    # 1) Fetch imagery and compute change mask
    run([sys.executable, os.path.join('notebooks', 'fetch_imagery.py'), str(minx), str(miny), str(maxx), str(maxy), tif_path])

    # 2) Process change mask into polygons
    run([sys.executable, os.path.join('notebooks', 'process_change.py'), tif_path, detected_geojson])

    # 3) Score zones with base severity and risk
    initial_scored = os.path.join(job_dir, 'scored_initial.geojson')
    run([sys.executable, os.path.join('notebooks', 'score_zones.py'), detected_geojson, initial_scored])

    # 4) Fetch auxiliary legal layers and apply hybrid legal scoring
    bhuvan_output = os.path.join('data', 'bhuvan_lulc.geojson')
    try:
        run([sys.executable, os.path.join('notebooks', 'fetch_bhuvan_lulc.py'), '--output', bhuvan_output])
    except Exception as e:
        print(f'Warning: Bhuvan LULC generation failed: {e}')

    try:
        run([sys.executable, os.path.join('notebooks', 'fetch_osm_layers.py'), '--output-dir', 'data'])
    except Exception as e:
        print(f'Warning: OSM layer export failed: {e}')

    run([sys.executable, os.path.join('notebooks', 'legal_cross_reference.py'), initial_scored, scored_geojson, '--bhuvan', bhuvan_output, '--data-dir', 'data'])

    # 5) Publish API JSON data for frontend and external clients
    run([sys.executable, os.path.join('notebooks', 'export_api_data.py')])

    # mark done
    open(os.path.join(job_dir, 'DONE'), 'w').write(str(time.time()))
    print('Pipeline finished')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('minx', type=float)
    parser.add_argument('miny', type=float)
    parser.add_argument('maxx', type=float)
    parser.add_argument('maxy', type=float)
    parser.add_argument('job_dir', type=str)
    args = parser.parse_args()
    main(args.minx, args.miny, args.maxx, args.maxy, args.job_dir)
