"""Fetch only main images matching the reviewed ABO sample; never full image archives."""
import csv
import gzip
import hashlib
import io
import json
import urllib.request
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = 'https://amazon-berkeley-objects.s3.amazonaws.com/'


def main():
    source = ROOT / 'data/public-catalogue/stage31/abo'
    output = ROOT / 'Simlect-front/Simlect-web/public/catalogue/abo'
    output.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in (source / 'sample.jsonl').read_text(encoding='utf8').splitlines()]
    needed = {row['main_image_id'] for row in rows}
    metadata = source / 'images.csv.gz'
    if not metadata.exists():
        with urllib.request.urlopen(BASE + 'images/metadata/images.csv.gz', timeout=40) as r:
            data = r.read(16 * 1024 * 1024 + 1)
        if len(data) > 16 * 1024 * 1024:
            raise ValueError('IMAGE_METADATA_LIMIT_EXCEEDED')
        metadata.write_bytes(data)
    with gzip.open(metadata, 'rt', encoding='utf8') as f:
        paths = {r['image_id']: r['path'] for r in csv.DictReader(f) if r['image_id'] in needed}
    if needed - paths.keys():
        raise ValueError('SOURCE_IMAGE_MAPPING_MISSING')
    manifest = []
    for row in rows:
        image = row['main_image_id']
        path = paths[image]
        url = BASE + 'images/small/' + path
        target = output / (row['item_id'] + Path(path).suffix)
        if not target.exists():
            for attempt in range(2):
                try:
                    with urllib.request.urlopen(url, timeout=35) as response:
                        data = response.read(256 * 1024 + 1)
                    break
                except Exception:
                    if attempt: raise
                    time.sleep(2)
            if len(data) > 256 * 1024 or not (data.startswith(b'\xff\xd8\xff') or data.startswith(b'\x89PNG\r\n')):
                raise ValueError('INVALID_OR_OVERSIZE_SOURCE_IMAGE')
            target.write_bytes(data)
        data = target.read_bytes()
        if len(data)>256*1024 or metadata.stat().st_size+sum(x['bytes'] for x in manifest)+len(data)>42*1024*1024:
            raise ValueError('TOTAL_SMALL_IMAGE_BUDGET_EXCEEDED')
        manifest.append({'sourceId': row['item_id'], 'imageId': image, 'sourceUrl': url,
                         'cover': '/catalogue/abo/' + target.name, 'bytes': len(data),
                         'sha256': hashlib.sha256(data).hexdigest(), 'license': 'CC-BY-4.0'})
        print(json.dumps({'downloaded': len(manifest), 'sourceId': row['item_id']}), flush=True)
    (source / 'images-manifest.json').write_text(json.dumps({'images': manifest, 'imageBytes': sum(x['bytes'] for x in manifest),
                                                          'metadataBytes': metadata.stat().st_size}, ensure_ascii=False, indent=2), encoding='utf8')


if __name__ == '__main__':
    main()
