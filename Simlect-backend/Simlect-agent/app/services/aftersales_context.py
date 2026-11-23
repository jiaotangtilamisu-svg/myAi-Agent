"""Scoped intent/reference memory. Cached order numbers never prove ownership."""
from app.auth.agent_context import current_agent_user
from app.domain.aftersales_intent import classify, resolve
from app.supervisor import store

async def prepare_turn(user_id, text):
    user=current_agent_user()
    if user is None or user.user_id!=user_id:return text,classify(text)
    try:previous=await store.hint(user_id)
    except Exception:previous={}
    resolved,intent=resolve(text,previous)
    if intent and intent['operation'] not in {'POLICY_QUERY','ORDER_QUERY','AFTERSALES_PROGRESS','CANCEL_APPLICATION'}:
        hint={'kind':'pending','businessIntent':intent['operation']}
        if intent.get('orderId'):hint['orderId']=intent['orderId']
        try:await store.save_hint(user_id,hint)
        except Exception:pass  # Explicit current requests still query ownership; never invent memory.
    return resolved,intent

async def load_case_progress(user_id, order_id=None):
    from app.auth.agent_context import require_agent_user
    from app.services.java_internal_client import java_internal_client
    require_agent_user(user_id)
    # Gateway owns the /api prefix; the existing Java user endpoint performs
    # login and case-owner validation using the trusted context's real token.
    rows=await java_internal_client.post_json('/api/order/aftersalesCase/list',{'orderId':order_id} if order_id else {},strict=True)
    if not isinstance(rows,list) or any(not isinstance(r,dict) or not all(isinstance(r.get(k),str) and r[k] for k in ('caseId','orderId','state')) for r in rows):raise ValueError('Invalid case progress')
    result=[{k:r.get(k) for k in ('caseId','orderId','state','version')} for r in rows[:20] if not order_id or r['orderId']==order_id]
    if order_id and result:
        # One detail read for the newest matching case, independent of list size.
        latest=result[0]
        try:
            detail=await java_internal_client.post_json('/api/order/aftersalesCase/detail',{'caseId':latest['caseId']},strict=True)
            if not isinstance(detail,dict) or detail.get('caseId')!=latest['caseId'] or detail.get('orderId')!=order_id:
                raise ValueError('Case detail identity mismatch')
            facts=detail.get('fulfillment') or {}
            latest['fulfillment']={k:facts.get(k) for k in ('refundStatus','refundMode','refundId','logisticsStatus','acceptance')}
            latest['progressDetailStatus']='SUCCESS'
        except Exception:
            latest['progressDetailStatus']='UNAVAILABLE'
    return result

def render_case_progress(rows):
    if not rows:return '当前账号在所查询范围内暂无售后申请。支付渠道退款记录与售后案件不同，不能据此确认资金是否到账。'
    labels={'AWAITING_USER':'等待本人确认','ADMIN_REVIEW':'待管理员审核','MANUAL_PENDING':'等待人工接单','IN_PROGRESS':'人工处理中','PROCESSING_FAILED':'处理失败，待人工核实','REJECTED':'已驳回','RESOLVED':'已处理','ARCHIVED':'已归档','CANCELLED':'已取消'}
    refunds={'NOT_EXECUTED':'未执行','PENDING':'待执行，尚未开始','PROCESSING':'处理中，尚未确认成功','SUCCEEDED':'成功（仅模拟，不代表资金到账）','FAILED':'失败，等待核实重试','UNKNOWN':'结果未知，须人工核实'}
    lines=['本人售后申请进度：']
    for row in rows:
        lines.append('订单 '+row['orderId']+'；案件 '+row['caseId']+'；'+labels.get(row['state'],'状态待核实'))
        f=row.get('fulfillment') or {}
        if row.get('progressDetailStatus')=='UNAVAILABLE':lines.append('履约详情暂不可用，不能据此判断退款成功或失败。')
        if f:
            lines.append('退货验收：'+({'ACCEPTED':'已通过','REJECTED':'未通过'}.get(f.get('acceptance'),'尚无验收记录')))
            prefix='本地模拟退款：' if f.get('refundMode')=='MOCK' else '案件退款执行记录：'
            lines.append(prefix+refunds.get(f.get('refundStatus'),'状态未知'))
            if f.get('logisticsStatus')!='NOT_REGISTERED' and not f.get('acceptance'):lines.append('下一步：请处理人在实际收到退货后登记验收；重复登记物流不会推进退款。')
    lines.append('以上是售后案件记录；模拟结果不等于原支付渠道退款或资金到账。可在下方案件卡片刷新详情。')
    return '\n'.join(lines)
