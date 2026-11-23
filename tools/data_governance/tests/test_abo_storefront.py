"""No-network tests for the reviewed real-image/local-price Product publication resource."""
import copy
import json
import shutil
from pathlib import Path

import pytest
from tools.data_governance.abo_storefront import ROOT, build


@pytest.fixture
def inputs(tmp_path):
    source = ROOT / 'data/public-catalogue/stage31/abo'
    for name in ('sample.jsonl','manifest.json','LICENSE-CC-BY-4.0.txt','images-manifest.json','test-prices.json'):
        shutil.copyfile(source/name,tmp_path/name)
    backup = ROOT / '.cache/stage31/storefront/database-backup/manifest.json'
    return tmp_path, backup


def test_hundred_products_use_actual_matching_images_and_local_prices(inputs):
    plan = build(*inputs)
    assert len(plan['products']) == 100
    assert len({p['productId'] for p in plan['products']}) == 100
    for p in plan['products']:
        assert p['productId'] == 'ABO'+p['sourceId']
        assert p['sourceId'] in p['cover']
        assert p['sourceImageUrl'].startswith('https://amazon-berkeley-objects.s3.amazonaws.com/images/small/')
        assert p['priceOrigin'] == 'MANUAL_LOCAL_STORE_PRICE'
        assert len(p['specification']) <= 100
        assert 'stock' not in p  # Unknown is not converted into invented availability.


def test_first_screen_includes_real_cups_and_headsets_not_only_phone_cases(inputs):
    plan=build(*inputs)
    hot=[p for p in plan['products'] if p['commendType']==1]
    assert len(hot)==10
    assert {p['kind'] for p in hot}=={'DRINKING_CUP','HEADPHONES','CELLULAR_PHONE_CASE'}
    assert not any(p['kind']=='CELLULAR_PHONE' for p in plan['products'])


def test_identical_input_produces_identical_publication_plan(inputs):
    assert build(*inputs)==build(*inputs)


def test_image_of_another_product_is_rejected(inputs):
    source,backup=inputs
    manifest=json.loads((source/'images-manifest.json').read_text())
    manifest['images'][0]['imageId']='wrong-product-image'
    (source/'images-manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='MATCHED_SOURCE_IMAGE_REQUIRED'):build(source,backup)


def test_incomplete_image_set_never_publishes_placeholder(inputs):
    source,backup=inputs
    manifest=json.loads((source/'images-manifest.json').read_text());manifest['images'].pop()
    (source/'images-manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='COMPLETE_MATCHED_IMAGES_AND_PRICES_REQUIRED'):build(source,backup)


def test_unknown_price_cannot_be_published_as_zero(inputs):
    source,backup=inputs
    prices=json.loads((source/'test-prices.json').read_text());prices['prices'][0]['testPriceCents']=None
    (source/'test-prices.json').write_text(json.dumps(prices))
    with pytest.raises(ValueError,match='INVALID_LOCAL_STORE_PRICE'):build(source,backup)


def test_invalid_backup_proof_prevents_publication(inputs):
    source,backup=inputs
    proof=json.loads(backup.read_text());proof['sha256']='0'*64
    bad=source/'bad-backup.json';bad.write_text(json.dumps(proof))
    with pytest.raises(ValueError,match='VERIFIED_BACKUP_REQUIRED'):build(source,bad)
