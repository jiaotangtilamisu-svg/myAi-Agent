export const caseStates = Object.freeze({AWAITING_USER:'等待用户确认',ADMIN_REVIEW:'待管理员审核',REJECTED:'已驳回',MANUAL_PENDING:'待人工处理',IN_PROGRESS:'处理中',PROCESSING_FAILED:'处理失败',RESOLVED:'已处理',ARCHIVED:'已归档',CANCELLED:'已取消'})
export function availableCaseActions(state, fulfillment) {
  if(state==='IN_PROGRESS' && ['refund','return_refund'].includes(fulfillment?.requestedType) && fulfillment.refundStatus!=='SUCCEEDED')return ['fail'];
  if(state==='IN_PROGRESS' && fulfillment?.refundStatus && !['NOT_EXECUTED','SUCCEEDED'].includes(fulfillment.refundStatus))return ['fail'];
  return ({ADMIN_REVIEW:['approve','reject'],MANUAL_PENDING:['claim'],IN_PROGRESS:['succeed','fail'],PROCESSING_FAILED:['retry'],CANCELLED:['archive'],RESOLVED:['archive'],REJECTED:['archive']})[state] || []
}
export function availableRefundActions(fulfillment={}) {
 const status=fulfillment.refundStatus || 'NOT_EXECUTED';
 if(['NOT_EXECUTED','FAILED'].includes(status))return ['prepareRefund'];
 if(status==='PENDING')return fulfillment.type==='return_refund' && fulfillment.acceptance!=='ACCEPTED'?[]:['startMockRefund'];
 if(status==='PROCESSING')return ['completeMockRefund','timeoutMockRefund'];
 if(status==='UNKNOWN')return ['completeMockRefund'];
 return [];
}
export function refundWorkflowGuide(row={}) {
 const f=row.fulfillment || {}, type=row.requestedType || f.type;
 if(row.state!=='IN_PROGRESS')return {title:caseStates[row.state] || '请核实案件状态',description:'先按当前案件状态完成本人确认、审核和人工接单；不会直接执行退款。'};
 if(type==='exchange')return {title:'人工换货处理中',description:'当前是人工换货申请，不提供退款执行操作。'};
 if(!['refund','return_refund'].includes(type))return {title:'人工处理中',description:'当前方案尚无已确认的退款类型，请按方案核实处理，不执行资金操作。'};
 if(type==='return_refund' && f.logisticsStatus==='NOT_REGISTERED')return {title:'第1步：登记退货物流',description:'尚无退货运单。登记物流只保存运单，不代表验收通过或退款成功。'};
 if(type==='return_refund' && f.acceptance==='REJECTED')return {title:'退货验收未通过，待人工核实',description:'请核对验收原因和补充材料，不能开始退款；如需重新验收，须填写新的实际核实意见。'};
 if(type==='return_refund' && f.acceptance!=='ACCEPTED')return {title:'第2步：登记退货验收',description:'物流已登记，请在实际收到退货后填写验收意见，勾选收到及验收结果，点击“登记退货验收”。重复登记物流不会完成验收。'};
 const status=f.refundStatus || 'NOT_EXECUTED';
 if(status==='SUCCEEDED')return {title:'本地模拟退款已成功',description:'这不是支付渠道资金到账。核对模拟结果后记录处理成功，再归档案件；原订单的支付状态不会被模拟结果改写。'};
 if(status==='UNKNOWN')return {title:'模拟结果未知，须人工核实',description:'不能盲目重试或标记成功。人工核实后勾选对应选项，再登记模拟结果。'};
 if(status==='PROCESSING')return {title:'第4步：登记模拟结果',description:'请填写结果说明，再登记成功、失败或超时未知；开始模拟不等于已经成功。'};
 if(row.capabilities?.mockRefundEnabled!==true)return {title:'履约条件已核实，模拟退款未启用',description:'本环境的模拟退款功能未启用或尚未确认，不能执行模拟；真实退款也不会由本页面执行。请联系系统管理员核实渠道接入，勿重复登记物流。'};
 return status==='PENDING'?{title:'第3步：开始本地模拟',description:'已准备模拟单，尚未执行。点击开始本地模拟后，还需填写并登记模拟结果；不会调用真实支付渠道。'}:{title:'第3步：准备本地模拟退款',description:'验收或仅退款条件核实后准备模拟单，再开始并登记模拟结果。失败重试沿用原模拟单号。'};
}
export function caseCommand(row, requestId, note) {
  if (!row?.caseId || !Number.isSafeInteger(row.version) || row.version<1 || !requestId || !note?.trim() || note.length>2000) throw new Error('请刷新案件并填写处理说明')
  return {caseId:row.caseId,expectedVersion:row.version,requestId,note:note.trim()}
}

export function fulfillmentNote(action, fields) {
 if(!['refund','return_refund'].includes(fields.type)) throw new Error('仅支持退款或退货退款');
 if(['returnLogistics','acceptReturn','returnProgress'].includes(action) && fields.type!=='return_refund')throw new Error('仅退货退款使用物流验收');
 if(action==='returnLogistics' && (!fields.carrier?.trim() || !/^(?=.*[A-Za-z0-9])[A-Za-z0-9-]{5,60}$/.test(fields.trackingNo || '')))throw new Error('请填写物流公司与有效运单号');
 if(['acceptReturn','returnProgress'].includes(action) && !fields.result?.trim())throw new Error('请填写核实意见');
 if(action==='returnProgress' && !['IN_TRANSIT','DELIVERED','EXCEPTION'].includes(fields.logisticsStatus))throw new Error('物流状态无效');
 if(action==='simulateRefund' && fields.simulateFailure && !fields.result?.trim())throw new Error('请填写模拟失败原因');
 if(['completeMockRefund','timeoutMockRefund'].includes(action) && !fields.result?.trim())throw new Error('请填写模拟结果或超时核实说明');
 if(action==='acceptReturn' && fields.received!==true)throw new Error('请先确认退货已收到');
 if(action==='completeMockRefund' && typeof fields.simulateFailure!=='boolean')throw new Error('请明确模拟成功或失败');
 return JSON.stringify({type:fields.type,carrier:fields.carrier?.trim(),trackingNo:fields.trackingNo?.trim(),accepted:fields.accepted===true,received:fields.received===true,condition:fields.condition || 'UNKNOWN',logisticsStatus:fields.logisticsStatus,result:fields.result?.trim(),simulateFailure:fields.simulateFailure===true,manualReconciliation:fields.manualReconciliation===true,evidenceRefs:fields.evidenceRefs || []});
}
