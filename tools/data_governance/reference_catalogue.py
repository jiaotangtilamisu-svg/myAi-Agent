"""Bounded, resumable anonymous catalogue snapshot. Never reads accounts/orders.

Only the user-selected Simlect public Product/file endpoints are allowed.
Source prices/SKUs are preserved; snapshots do not assert supplier availability.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = 'https://www.simlect.com'
_lock = threading.Lock()
_last = 0.0
_clients = threading.local()


def fetch(path, params=None, cap=2_000_000):
    global _last
    if path not in {'/api/product/loadCategory', '/api/product/loadCommendProduct',
                    '/api/product/loadProduct', '/api/product/getProduct'} and not path.startswith('/api/file/getResource?'):
        raise ValueError('PUBLIC_ENDPOINT_REQUIRED')
    with _lock:
        time.sleep(max(0, .25 - (time.monotonic() - _last)))
        _last = time.monotonic()
    body = urlencode(params).encode() if params is not None else None
    headers = {'User-Agent': 'Simlect-local-catalogue/1.0', 'Content-Type': 'application/x-www-form-urlencoded'}
    # Reuse connections; one TLS handshake per record is both slow and wasteful.
    import httpx
    if not hasattr(_clients, 'client'):
        _clients.client = httpx.Client(timeout=30, follow_redirects=False)
    with _clients.client.stream('POST' if body is not None else 'GET', BASE + path, content=body, headers=headers) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > cap:
                raise ValueError('SOURCE_SIZE_LIMIT')
            chunks.append(chunk)
        data = b''.join(chunks)
    if len(data) > cap:
        raise ValueError('SOURCE_SIZE_LIMIT')
    return data


def json_response(path, params=None):
    value = json.loads(fetch(path, params))
    if value.get('code') != 200:
        raise ValueError('SOURCE_BUSINESS_ERROR')
    return value['data']


def snapshot(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    def cached(name, path, params=None):
        dest = directory / name
        if dest.exists():
            return json.loads(dest.read_text(encoding='utf8'))
        value = json_response(path, params)
        dest.write_text(json.dumps(value, ensure_ascii=False), encoding='utf8')
        return value
    categories = cached('categories.json', '/api/product/loadCategory')
    recommended = cached('recommended.json', '/api/product/loadCommendProduct')
    first = cached('page-1.json', '/api/product/loadProduct', {'pageNo': 1})
    if not 0 < first['totalCount'] <= 800 or first['pageTotal'] > 60:
        raise ValueError('CATALOGUE_LIMIT_REVIEW_REQUIRED')
    pages = [first]
    def page_data(page):
        return cached(f'page-{page}.json', '/api/product/loadProduct', {'pageNo': page})
    with ThreadPoolExecutor(max_workers=4) as pool:
        pages.extend(pool.map(page_data, range(2, first['pageTotal'] + 1)))
    rows = {p['productId']: p for page in pages for p in page['list']}
    rows.update({p['productId']: p for p in recommended})
    if len(rows) > 800:
        raise ValueError('CATALOGUE_LIMIT_REVIEW_REQUIRED')
    detail_dir = directory / 'details'
    detail_dir.mkdir(exist_ok=True)
    def detail(pid):
        return cached(f'details/{pid}.json', '/api/product/getProduct', {'productId': pid})
    with ThreadPoolExecutor(max_workers=4) as pool:
        details = list(pool.map(detail, sorted(rows)))
    for d in details:
        validate_product(d)
    manifest = {'source': BASE, 'observedAt': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                'products': len(details), 'categories': len(categories),
                'skuCount': sum(len(d['skuList']) for d in details),
                'files': {str(f.relative_to(directory)): hashlib.sha256(f.read_bytes()).hexdigest()
                          for f in directory.rglob('*.json') if f.name != 'manifest.json'},
                'notice': 'Reference-site snapshot, not an ERP feed or verified supplier stock.'}
    (directory / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf8')
    return manifest


def validate_product(d):
    p = d['productInfo']
    if not str(p['productId']).isdigit() or len(str(p['productId'])) > 15:
        raise ValueError('INVALID_PRODUCT_ID')
    if not p.get('productName') or len(p['productName']) > 200:
        raise ValueError('INVALID_PRODUCT_NAME')
    if not isinstance(d.get('skuList'), list) or not 1 <= len(d['skuList']) <= 100:
        raise ValueError('INVALID_SKUS')
    if len({s['propertyValueIdHash'] for s in d['skuList']}) != len(d['skuList']):
        raise ValueError('DUPLICATE_SKUS')
    return d


def prepare(directory, backup, assets, resource):
    """Prepare an immutable administrator-reviewed import; no DB writes."""
    from decimal import Decimal
    directory, backup, assets, resource = map(Path, (directory, backup, assets, resource))
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf8'))
    proof = json.loads(backup.read_text(encoding='utf-8-sig'))
    if hashlib.sha256(Path(proof['file']).read_bytes()).hexdigest() != proof['sha256']:
        raise ValueError('VERIFIED_BACKUP_REQUIRED')
    for name, digest in manifest['files'].items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise ValueError('SOURCE_SNAPSHOT_CHANGED')
    categories = json.loads((directory / 'categories.json').read_text(encoding='utf8'))
    products = []
    for file in sorted((directory / 'details').glob('*.json')):
        d = validate_product(json.loads(file.read_text(encoding='utf8')))
        if d['productInfo'].get('status') != 1:
            raise ValueError('SOURCE_PRODUCT_NOT_ON_SALE')
        if any(s.get('productId') != d['productInfo']['productId'] for s in d['skuList']):
            raise ValueError('SKU_PRODUCT_MISMATCH')
        for s in d['skuList']:
            if s.get('price') is not None and Decimal(str(s['price'])) < 0:
                raise ValueError('NEGATIVE_PRICE')
            if s.get('stock') is not None and (type(s['stock']) is not int or not 0 <= s['stock'] <= 1_000_000):
                raise ValueError('INVALID_SOURCE_STOCK')
        d['sourceSha256'] = hashlib.sha256(file.read_bytes()).hexdigest()
        products.append(d)
    assets.mkdir(parents=True, exist_ok=True)
    images = {}
    image_locks = {}
    def mirror(source):
        if not __import__('re').fullmatch(r'[A-Za-z0-9_./-]+', source) or '..' in source:
            raise ValueError('UNSAFE_SOURCE_IMAGE')
        name = hashlib.sha256(source.encode()).hexdigest()[:24]+'.img'
        with image_locks.setdefault(name, threading.Lock()):
            dest=assets/name
            if not dest.exists():
                dest.write_bytes(fetch('/api/file/getResource?'+urlencode({'sourceName':source}),cap=3_000_000))
            data=dest.read_bytes()
            if len(data)<100 or data[:1] in {b'<',b'{'}:
                raise ValueError('INVALID_IMAGE_RESPONSE')
        return name,data
    def cover(d):
        p = d['productInfo']
        paths = [x for x in (p.get('cover') or '').split(',') if x]
        if not paths:
            raise ValueError('SOURCE_IMAGE_MISSING')
        first = paths[0]
        if not __import__('re').fullmatch(r'[A-Za-z0-9_./-]+', first) or '..' in first:
            raise ValueError('UNSAFE_SOURCE_IMAGE')
        name,data = mirror(first)
        images[p['productId']] = {'source':BASE+'/api/file/getResource?'+urlencode({'sourceName':first}),
                                  'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
        if sum(f.stat().st_size for f in assets.glob('*.img')) > 300_000_000:
            raise ValueError('TOTAL_IMAGE_LIMIT')
        p['cover'] = ','.join(['catalogue/reference/'+name] + [BASE+'/api/file/getResource?'+urlencode({'sourceName':v}) for v in paths[1:]])
        p['productDesc'] = (p.get('productDesc') or '').replace('](/api/file/', ']('+BASE+'/api/file/')
        for prop in d.get('productPropertyList', []):
            for value in prop.get('propertyValues', []):
                if value.get('propertyCover'):
                    image,_ = mirror(value['propertyCover'])
                    value['propertyCover']='catalogue/reference/'+image
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(cover, products))
    fingerprint = hashlib.sha256(json.dumps(manifest['files'],sort_keys=True).encode()).hexdigest()
    plan = {'planId':'REF31_'+fingerprint[:32], 'source':BASE, 'observedAt':manifest['observedAt'],
            'categories':categories,'products':products,'backupFile':proof['file'],'backupSha256':proof['sha256'],
            'images':images,'notice':'参考站公开目录快照：商品、SKU、图片、售价逐项对应；本地库存仅为本机体验配置，不代表供应商实时库存。'}
    resource.parent.mkdir(parents=True,exist_ok=True)
    resource.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf8')
    return {'products':len(products),'skus':sum(len(p['skuList']) for p in products),'planId':plan['planId'],
            'imageBytes':sum(v['bytes'] for v in images.values()),'resource':str(resource)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(snapshot(args.output), ensure_ascii=False))


if __name__ == '__main__':
    main()
