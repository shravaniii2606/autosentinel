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
    legal_geojson = os.path.join(job_dir, 'legal_verified_zones.geojson')

    # 1) Fetch imagery and compute change mask
    run([sys.executable, os.path.join('notebooks', 'fetch_imagery.py'), str(minx), str(miny), str(maxx), str(maxy), tif_path])

    # 2) Process change mask into polygons
    run([sys.executable, os.path.join('notebooks', 'process_change.py'), tif_path, detected_geojson])

    # 3) Score zones
    run([sys.executable, os.path.join('notebooks', 'score_zones.py'), detected_geojson, scored_geojson])

    # 3.5) Check zones against legal/protected layers (forest, wetland, etc.)
    # Non-fatal: if OSM is unreachable or all layers are unavailable, the
    # script still runs and just leaves final_risk_score == risk_score.
    try:
        run([sys.executable, os.path.join('notebooks', 'legal_zone_check.py'), scored_geojson, legal_geojson])
    except Exception as e:
        print(f"Legal zone check skipped: {e}")

    # 4) Optionally generate reports for each zone (could be slow)
    # We'll generate report files for each detected zone in scored_geojson
    try:
        import geopandas as gpd
        gdf = gpd.read_file(scored_geojson)
        for idx, row in gdf.iterrows():
            # call the existing generate_report script which expects a zone id
            # We'll write a small JSON to data/flagged_zones.json so generator can find details
            # For now, skip report generation to avoid complexity
            pass
    except Exception as e:
        print('Skipping report generation:', e)

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