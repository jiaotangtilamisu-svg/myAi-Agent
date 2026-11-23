export function caseGuidance(state: string): string {
 const steps: Record<string,string> = {
  AWAITING_USER:'请核对方案并填写真实原因，确认后才会提交申请。',
  ADMIN_REVIEW:'申请已提交，正在等待管理员审核。无需重复提交；可刷新进度查看审核结果。',
  REJECTED:'申请未通过，请查看审核原因；补充真实材料后可以重新提交。',
  MANUAL_PENDING:'审核已通过，等待工作人员接单；尚未执行退款。',
  IN_PROGRESS:'工作人员正在处理。退货退款须按审核要求寄回并验收；仅退款无需寄回。',
  PROCESSING_FAILED:'本次处理未完成，工作人员需核实失败原因并按原业务单重试；请勿重复申请。',
  RESOLVED:'案件处理已完成。案件完成不等于资金到账，请核对实际退款记录及支付渠道状态。',
  CANCELLED:'申请已取消，订单和资金未变更。如需重新申请，请查询订单生成新方案。',
  ARCHIVED:'案件已归档，可查看完整处理记录。'
 };
 return steps[state] || '暂无法识别处理状态，请刷新或联系人工客服核实。';
}
export function caseFulfillmentGuidance(row: {state?:string;requestedType?:string;capabilities?:{mockRefundEnabled?:boolean};fulfillment?:{acceptance?:string;refundStatus?:string;logisticsStatus?:string}}): string {
 const f=row.fulfillment || {};
 if(f.refundStatus==='SUCCEEDED')return '本地模拟退款处理成功，不代表原支付渠道已退款；原订单支付状态不会由模拟结果改写。';
 if(row.state!=='IN_PROGRESS')return '';
 if(row.requestedType==='return_refund' && f.acceptance==='REJECTED')return '退货验收未通过，等待工作人员核实原因和补充材料；当前没有退款成功记录。';
 if(row.requestedType==='return_refund' && f.acceptance!=='ACCEPTED')return f.logisticsStatus==='NOT_REGISTERED'?'请在审核要求下实际寄回后登记退货物流。':'退货物流已登记，等待工作人员实际收货并登记验收。登记物流不等于验收或退款成功。';
 if(f.refundStatus==='PENDING')return '已生成待执行模拟单，尚未执行，不是退款失败或资金到账。'+(row.capabilities?.mockRefundEnabled===true?'工作人员还需开始模拟并登记结果。':'本环境未启用或尚无法确认模拟执行能力，请工作人员核实配置；不会自动调用真实支付渠道。');
 return '';
}
export function caseOperationError(error: unknown): string {
 if(error === 'cancel' || error === 'close') return '';
 const e=error as {code?:number;info?:unknown;response?:{status?:number}} | null;
 if(e?.response?.status === 409) return '申请已被更新，请刷新进度后再操作，避免重复提交。';
 if(e?.code===901 || e?.response?.status===401) return '登录已失效，请重新登录后查询申请。';
 return '操作未完成，请刷新申请进度或联系人工客服核实；请勿重复提交。本次未确认退款执行成功。';
}

export function caseTimelineNote(event: {action?:string;note?:string}): string {
 try {
  const n=JSON.parse(event.note || '');
  if(['CONFIRM','AMEND'].includes(event.action || ''))return `申请原因：${String(n.reason || '已确认申请')}`;
  if(['RETURN_LOGISTICS','USER_RETURN_LOGISTICS'].includes(event.action || ''))return `退货物流：${n.carrier}，运单号：${n.trackingNo}`;
  if(event.action==='RETURN_PROGRESS')return `物流人工核实：${n.result || '已更新'}`;
  if(event.action==='RETURN_ACCEPT')return `退货验收${n.accepted?'通过':'未通过'}：${n.result}`;
  if(event.action==='MOCK_REFUND')return `本地模拟退款${n.status==='SUCCEEDED'?'成功':'失败，等待人工重试'}；不代表真实资金到账。`;
  if(['PREPARE_REFUND','START_MOCK_REFUND','COMPLETE_MOCK_REFUND','TIMEOUT_MOCK_REFUND'].includes(event.action || ''))return `本地模拟退款：${({PENDING:'待执行',PROCESSING:'处理中',SUCCEEDED:'成功',FAILED:'失败',UNKNOWN:'结果未知，须人工核实'} as Record<string,string>)[n.status] || '待核实'}；不代表真实资金到账。`;
  return '处理记录已更新，可查看方案详情。';
 }catch{return event.note || '';}
}

export function applicationDraft(row: {applicationReason?:string;applicationMaterials?:string[];requestedType?:string}) {
 return {reason:row.applicationReason || '',materials:[row.applicationMaterials?.[0] || '',row.applicationMaterials?.[1] || ''],requestedType:row.requestedType || 'return_refund'};
}
export function applicationPayload(reason:string,materials:string[],requestedType:string) {
 if(!reason.trim() || reason.length>1000 || !['refund','return_refund','exchange'].includes(requestedType) || materials.length>2 || materials.some(m=>m.length>350))throw new Error('申请原因、类型或材料不符合要求');
 return JSON.stringify({reason:reason.trim(),materials:materials.map(m=>m.trim()).filter(Boolean),requestedType});
}
