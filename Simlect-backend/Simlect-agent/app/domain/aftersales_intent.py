"""Shared business intent contract, not a response generator or executor.

Compose action/object/query grammar and validated order references once. Existing
LLM intent handling remains the fallback for unsupported utterances; this module
never invents order identifiers, identity, eligibility, or financial permission.
"""
import re
import unicodedata
from app.utils.order_ids import extract_order_id as existing_order_id

OPERATIONS = {'RETURN','REFUND','EXCHANGE','CANCEL_ORDER','CANCEL_APPLICATION',
              'ORDER_QUERY','ORDER_DETAIL','LOGISTICS_QUERY','POLICY_QUERY','AFTERSALES_PROGRESS'}
APPLICATIONS = {'RETURN','REFUND'}
VERBS = {'RETURN':'退货','REFUND':'退款','EXCHANGE':'换货','CANCEL_ORDER':'取消订单','CANCEL_APPLICATION':'取消售后申请',
         'ORDER_QUERY':'查询我的订单列表','ORDER_DETAIL':'查询订单详情','LOGISTICS_QUERY':'查询订单物流','AFTERSALES_PROGRESS':'查询售后申请进度'}

def order_ids(text):
    found=[]
    for token in re.findall(r'[A-Za-z0-9_-]+',text or ''):
        value=existing_order_id(token)
        if value:found.append(value)
    # Preserve compatibility with explicitly labelled short business/test IDs.
    found += re.findall(r'(?:订单号|订单编号|orderId|订单)\s*[:：=#]?\s*([A-Za-z0-9][A-Za-z0-9_-]{0,63})(?![A-Za-z0-9_-])',text or '',re.I)
    return list(dict.fromkeys(existing_order_id(v) or v for v in found))

def classify(text):
    if not isinstance(text,str) or not text.strip() or len(text)>2000:return None
    text=unicodedata.normalize('NFKC',text)
    ids=order_ids(text)
    surface=text
    for oid in sorted(ids,key=len,reverse=True):surface=surface.replace(oid,'订单')
    op=None
    # Query/negation qualifiers distinguish advice from an application request.
    policy=bool(re.search(r'政策|规则|条款|规定|无理由',surface) or re.search(r'(?:七|7)[天日]',surface) and re.search(r'退|换|售后|保修|维修',surface))
    no_submit=bool(re.search(r'(?:不要|不用|不必|别)\s*(?:直接|自动)?\s*(?:提交|申请|办理|执行)',surface))
    negated_action=bool(re.search(r'(?:不要|不用|不必|别|暂不)\s*(?:给我|帮我|直接|自动)?\s*(?:退款|退货|换货|取消订单)',surface))
    if negated_action:op='ORDER_DETAIL' if ids else 'POLICY_QUERY'
    elif re.search(r'(?:取消|撤销|撤回).{0,8}(?:申请|售后|案件)',surface):op='CANCEL_APPLICATION'
    elif re.search(r'(?:售后|退货|退换|申请|退款).{0,8}(?:进度|进程|进展|到哪一步|处理结果|办理状态|到账|没到|未到)|(?:查询|查看|跟踪).{0,6}(?:售后申请|售后案件|退款)',surface):op='AFTERSALES_PROGRESS'
    elif re.search(r'(?:取消|关闭|撤销).{0,8}订单|订单.{0,8}(?:取消|关闭)',surface):op='CANCEL_ORDER'
    elif (policy or no_submit) and not ids:op='POLICY_QUERY'
    elif re.search(r'换货|(?:想|要|帮我|给我).{0,5}换(?:这个|商品|订单|货|掉)',surface):op='EXCHANGE'
    elif re.search(r'退款|退钱|退费',surface):op='REFUND'
    elif re.search(r'(?:订单|商品|东西).{0,8}(?:还能|能不能|能否|可不可以|是否能|可以).{0,3}退',surface):op='RETURN'
    elif re.fullmatch(r'(?:请|帮我|麻烦|我要|我想|我想要)?退(?:一下|一退|掉|了)[。？！!?]*',surface) or re.search(r'退货|(?:退|退掉|退了)(?:一?下|一退)?(?:这|那|个|笔|单|订单|商品|东西|货|掉|了)|(?:商品|东西|货).{0,6}(?:退了|退掉)|(?:商品|东西|订单).{0,8}(?:不想要|不要了)|买错.{0,10}退',surface):op='RETURN'
    elif re.search(r'物流|快递|包裹|配送|送到',surface):op='LOGISTICS_QUERY'
    elif policy:op='POLICY_QUERY'
    elif re.search(r'(?:如何|怎么|怎样|咋).{0,5}(?:申请|办理).{0,3}售后',surface):op='POLICY_QUERY'
    elif re.search(r'订单.{0,6}(?:详情|明细|商品|状态)',surface) or ids:op='ORDER_DETAIL'
    elif re.search(r'(?:查询|查看|看看|列出|查一下|查查|我的|本人).{0,8}订单|订单列表',surface):op='ORDER_QUERY'
    if not op:return None
    return {'operation':op,'orderId':ids[0] if len(ids)==1 else None,'orderIds':ids,
            'progressQueryOnly':op=='AFTERSALES_PROGRESS' and not bool(re.search(r'异常|一直|迟迟|长时间|失败|没到账|未到账|未退款|卡住',surface)),
            'ambiguousOrder':len(ids)>1,'progressKind':'refund' if re.search(r'退款|到账',surface) else 'case','requiresOrder':op not in {'ORDER_QUERY','POLICY_QUERY','AFTERSALES_PROGRESS','CANCEL_APPLICATION'},
            'source':'VALIDATED_ACTION_OBJECT_GRAMMAR'}

def resolve(text, previous):
    """Restore only explicit references or an order-number-only pending answer."""
    result=classify(text)
    previous=previous if isinstance(previous,dict) else {}
    pending=previous.get('businessIntent')
    ids=order_ids(text)
    only_id=bool(ids) and not re.sub(r'(?:订单号|订单编号|订单|orderId)|[\s:：=#，,。！？?!；;]|'+ '|'.join(re.escape(v) for v in ids),'',text,flags=re.I)
    if pending in OPERATIONS and only_id and len(ids)==1:
        text=VERBS.get(pending,'查询订单')+'；订单号：'+ids[0];result=classify(text)
    elif pending in OPERATIONS and re.fullmatch(r'(?:继续|然后呢|这单呢|刚才那个呢)[。？?!]*',text.strip()):
        text=VERBS.get(pending,'查询订单')+('；订单号：'+previous['orderId'] if previous.get('orderId') else '')
        result=classify(text)
    elif result and (result['requiresOrder'] or result['operation']=='AFTERSALES_PROGRESS') and not ids and previous.get('orderId') and re.search(r'这笔|这单|这个订单|该订单|刚才.*订单|它',text):
        text+='；订单号：'+previous['orderId'];result=classify(text)
    return text,result
