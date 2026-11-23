import json
import pytest
from tools.data_governance.reference_catalogue import validate_product, fetch

def row():
    return {'productInfo':{'productId':'317209961074372','productName':'商品'},
            'skuList':[{'propertyValueIdHash':'a'*32,'price':None,'stock':None}]}

def test_unknown_price_and_stock_remain_null():
    d=validate_product(row())
    assert d['skuList'][0]['price'] is None and d['skuList'][0]['stock'] is None

@pytest.mark.parametrize('id',['../123','ABCD','1'*16])
def test_invalid_product_id(id):
    d=row();d['productInfo']['productId']=id
    with pytest.raises(ValueError):validate_product(d)

def test_duplicate_sku_rejected():
    d=row();d['skuList']*=2
    with pytest.raises(ValueError):validate_product(d)

@pytest.mark.parametrize('path',['/api/order/loadOrder','/api/account/login','https://other.example'])
def test_never_downloads_private_or_third_party_endpoints(path):
    with pytest.raises(ValueError,match='PUBLIC_ENDPOINT_REQUIRED'):fetch(path)
