"""Prepare a reviewed Product-service publication resource. No database writes."""
import hashlib
import json
import shutil
from pathlib import Path
from .abo_sample import inspect

ROOT = Path(__file__).resolve().parents[2]


def build(directory, backup):
    directory, backup = Path(directory), Path(backup)
    report, records = inspect(directory)
    if report['status'] != 'VALID':
        raise ValueError('VALID_ABO_SOURCE_REQUIRED')
    proof = json.loads(backup.read_text(encoding='utf-8-sig'))
    dump = Path(proof['file'])
    if hashlib.sha256(dump.read_bytes()).hexdigest() != proof['sha256']:
        raise ValueError('VERIFIED_BACKUP_REQUIRED')
    images = json.loads((directory / 'images-manifest.json').read_text(encoding='utf8'))['images']
    prices = json.loads((directory / 'test-prices.json').read_text(encoding='utf8'))['prices']
    if len(images) != 100 or len(prices) != 100:
        raise ValueError('COMPLETE_MATCHED_IMAGES_AND_PRICES_REQUIRED')
    by_image = {x['sourceId']: x for x in images}
    by_price = {x['sourceId']: x for x in prices}
    products = []
    for _, source_id, text, _ in records:
        p = json.loads(text)
        image, price = by_image[source_id], by_price[source_id]
        path = ROOT / 'Simlect-front/Simlect-web/public' / image['cover'].lstrip('/')
        if image['imageId'] != p['mainImageId'] or hashlib.sha256(path.read_bytes()).hexdigest() != image['sha256']:
            raise ValueError('MATCHED_SOURCE_IMAGE_REQUIRED')
        if type(price['testPriceCents']) is not int or price['testPriceCents'] <= 0:
            raise ValueError('INVALID_LOCAL_STORE_PRICE')
        kind = p['originalProductType']
        attributes = [str(v) for v in p['attributes'].values() if v]
        spec = ' / '.join(attributes)[:100] or '标准款'
        products.append({'productId': 'ABO' + source_id, 'sourceId': source_id,
                         'productName': p['productName'][:200], 'cover': image['cover'].lstrip('/'),
                         'categoryId': {'CELLULAR_PHONE_CASE': 'A311', 'DRINKING_CUP': 'A312', 'HEADPHONES': 'A313'}[kind],
                         'price': f"{price['testPriceCents']/100:.2f}", 'priceOrigin': 'MANUAL_LOCAL_STORE_PRICE',
                         'skuHash': hashlib.md5(b'ABO_STD',usedforsecurity=False).hexdigest(),
                         'specification': spec, 'sourceImageUrl': image['sourceUrl'], 'imageSha256': image['sha256'],
                         'productDesc': f"{p['productName']}\n{spec}\n商品资料与图片来源：Amazon Berkeley Objects / Amazon.com，CC BY 4.0。{p['sourceUrl']}\n本商城自主定价，非Amazon当前报价。库存待核实。", 'kind': kind})
    # Put two actual cups and two actual headsets into the first screen, never label cases as phones.
    products.sort(key=lambda p: ({'DRINKING_CUP': 0, 'HEADPHONES': 1, 'CELLULAR_PHONE_CASE': 2}[p['kind']], p['sourceId']))
    for i, p in enumerate(products):
        p['commendType'] = 1 if i < 10 else 0
    return {'planId': 'ABO31_STOREFRONT_V1', 'license': 'CC-BY-4.0', 'products': products,
            'sourceBatch': report['batchId'], 'backupFile': str(dump), 'backupSha256': proof['sha256'],
            'notice': 'ABO名称和真实图片；售价由本商城自行设定，不是Amazon商业报价。未创建库存；旧演示商品仅下架保留。'}


def main():
    source = ROOT / 'data/public-catalogue/stage31/abo'
    backup = ROOT / '.cache/stage31/storefront/database-backup/manifest.json'
    plan = build(source, backup)
    target = ROOT / 'Simlect-backend/Simlect-product/app/src/main/resources/catalogue/abo-storefront.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf8')
    out = ROOT / 'data/simlect/upload/file/catalogue/abo'
    out.mkdir(parents=True, exist_ok=True)
    for p in plan['products']:
        image = ROOT / 'Simlect-front/Simlect-web/public' / p['cover']
        destination = out / image.name
        if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() != p['imageSha256']:
            raise ValueError('EXISTING_IMAGE_CONFLICT')
        if not destination.exists(): shutil.copyfile(image, destination)
    print(json.dumps({'products': len(plan['products']), 'resource': str(target), 'stockCreated': 0}))


if __name__ == '__main__':
    main()
