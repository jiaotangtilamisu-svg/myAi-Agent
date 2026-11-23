import pytest
from app.rag.aftersales_topics import topic,applicable
from app.config.settings import Settings
from app.shopping.selection import select
from test_stage28_quality import cup

@pytest.mark.parametrize('query,expected',[('网购七天无理由退货有什么条件','NO_REASON'),('商品质量问题可以退货吗','QUALITY'),('退货运费由谁承担','FREIGHT'),('商品已经拆封还能退吗','OPENED'),('商城承诺的售后期限在哪里查询','SHOP_PROMISE')])
def test_topic(query,expected):assert topic(query)==expected

def test_eighteenth_article_not_sufficient_for_no_reason_question():
 assert not applicable('超过七天还能退吗',{'text':'经营者应当标明真实名称和标记'})
 assert applicable('超过七天还能退吗',{'text':'TEST ONLY 七日无理由退货相关条款'})

def test_law_is_not_platform_promise():
 assert not applicable('商城承诺的售后期限在哪里查询',{'text':'TEST ONLY 七日无理由退货','category':'LAW'})

def test_real_default_and_unknown_exclusion():
 assert Settings.model_fields['shopping_data_mode'].default=='REAL'
 assert not select([cup()],{},data_mode='REAL')['recommendations']
def test_official_preview_only_extracts_one_body(tmp_path):
 from tools.data_governance.official_policy_preview import prepare
 p=tmp_path/'official.html';p.write_text('<div id="UCAP-CONTENT"><p>第一条 TEST ONLY</p><p>第二条 TEST ONLY</p></div><p>第一条 DUPLICATE MOBILE</p>',encoding='utf8')
 r=prepare(p,'https://example.invalid/official')
 assert len(r['articles'])==2 and 'DUPLICATE' not in r['text']
 assert r['state']=='LOCAL_PREVIEW_NOT_IMPORTED'

def test_keyword_vector_filter_does_not_lower_threshold():
 from app.rag.aftersales_topics import keyword_filter
 f=keyword_filter('网购商品七日无理由退货')
 assert f['bool']['minimum_should_match']==1
 assert any('无理由' in str(c) for c in f['bool']['should'])
