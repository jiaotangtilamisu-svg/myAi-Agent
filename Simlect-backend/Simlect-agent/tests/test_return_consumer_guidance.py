from app.services.aftersales_diagnosis import render_diagnosis,mark_return_request
from test_return_application_presentation import diagnosis

def test_return_answer_is_actionable_not_policy_wall():
 r=diagnosis();mark_return_request(r);text=render_diagnosis(r)
 assert '生成待确认的售后方案' in text and '仅退款' in text
 assert '距下单' not in text and len(text)<650
 assert r['policyEvidence']['status']=='LOW_RELEVANCE'

def test_shipped_return_does_not_promise_refund():
 r=diagnosis();r['orderFacts']['data']['orderStatus']=2;mark_return_request(r)
 text=render_diagnosis(r)
 assert '不要自行寄回' in text and '不会自动划款' in text

def test_unverified_return_never_shows_submission_instructions():
 r=diagnosis();r['orderFacts']['queryStatus']='NOT_FOUND';mark_return_request(r)
 assert '才能生成' in render_diagnosis(r)
