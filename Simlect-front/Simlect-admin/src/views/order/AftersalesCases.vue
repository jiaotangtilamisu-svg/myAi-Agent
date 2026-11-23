<template>
 <section class="cases"><h2>售后案件与人工处理</h2>
 <el-alert title="审批仅进入人工处理，不执行退款、支付或发货。操作权限及状态由服务端校验。" type="warning" :closable="false" />
 <div class="tools"><el-select v-model="state" clearable placeholder="全部状态" style="width:200px"><el-option v-for="(label,key) in caseStates" :key="key" :label="label" :value="key" /></el-select><el-button @click="page=1;load()">查询</el-button></div>
 <el-alert v-if="error" :title="error" type="error" :closable="false" />
 <el-table :data="rows" v-loading="loading" border><el-table-column prop="caseId" label="案件编号" min-width="260"/><el-table-column prop="orderId" label="订单" min-width="180"/><el-table-column label="状态"><template #default="{row}">{{caseStates[row.state] || '状态待核实'}}</template></el-table-column><el-table-column prop="risk" label="风险"/><el-table-column prop="version" label="案件版本"/><el-table-column prop="planVersion" label="方案版本"/><el-table-column label="详情"><template #default="{row}"><el-button link @click="detail(row.caseId)">查看</el-button></template></el-table-column></el-table>
 <div class="tools"><el-button :disabled="page===1" @click="page--;load()">上一页</el-button><span>第{{page}}页</span><el-button :disabled="rows.length<20" @click="page++;load()">下一页</el-button></div>
 <el-dialog v-model="open" title="案件详情与审计" width="min(1100px, 94vw)" top="4vh" :close-on-click-modal="false"><template v-if="current">
 <p>案件 {{current.caseId}} · {{caseStates[current.state]}} · 版本 {{current.version}}</p>
 <p>订单：{{current.orderId}} · 申请原因：{{current.applicationReason || '尚未确认'}}</p>
 <ul><li v-for="(material,i) in current.applicationMaterials || []" :key="i">申请材料：{{material}}</li></ul>
 <div class="case-workbench"><el-alert :title="guide.title" :description="guide.description" type="info" :closable="false"/><el-alert v-if="dialogError" :title="dialogError" role="alert" type="error" :closable="false"/><el-alert v-if="notice" :title="notice" type="success" :closable="false"/> <el-input v-model="note" type="textarea" maxlength="2000" show-word-limit placeholder="填写审批理由或实际人工处理结果；不代表系统已执行退款" aria-label="处理或验收意见"/>
 <div class="tools"><el-button v-for="a in availableCaseActions(current.state,current.fulfillment)" :key="a" :disabled="operating" @click="operate(a)">{{labels[a]}}</el-button></div>
 <fieldset v-if="current.state==='IN_PROGRESS' && current.requestedType!=='exchange'"><legend>退货履约记录与模拟退款</legend>
 <el-alert :title="mockEnabled?'本环境仅支持本地模拟，不产生真实资金操作。':'本环境模拟退款未启用或无法确认；不会执行真实渠道退款。'" :closable="false"/>
 <el-select v-model="fulfillmentType"><el-option label="仅退款" value="refund"/><el-option label="退货退款" value="return_refund"/></el-select>
 <el-input v-model="carrier" placeholder="退货物流公司"/><el-input v-model="trackingNo" placeholder="退货运单号"/>
 <el-select v-model="logisticsStatus"><el-option label="运输中" value="IN_TRANSIT"/><el-option label="已送达" value="DELIVERED"/><el-option label="运输异常" value="EXCEPTION"/></el-select>
 <el-button :disabled="operating || !hasTracking || !!current.fulfillment?.acceptance" @click="operate('returnProgress')">登记人工核实的物流进度/异常</el-button>
 <el-checkbox v-model="simulateFailure">模拟渠道失败（需填写失败原因，仅隔离环境启用）</el-checkbox>
<el-input v-model="acceptanceEvidence" maxlength="200" placeholder="可选：关联仓库验收记录或证据编号"/>
 <el-checkbox v-model="received">确认退货已收到</el-checkbox><el-select v-model="returnCondition"><el-option label="完好" value="INTACT"/><el-option label="有损坏" value="DAMAGED"/><el-option label="情况待确认" value="UNKNOWN"/></el-select>
 <el-checkbox v-model="accepted">验收通过</el-checkbox>
 <el-button :disabled="operating || !canRegisterTracking" @click="operate('returnLogistics')">{{hasTracking?'更正退货物流（需说明）':'登记退货物流'}}</el-button>
 <el-button :disabled="operating || !hasTracking || !['NOT_EXECUTED','PENDING'].includes(current.fulfillment?.refundStatus || 'NOT_EXECUTED')" @click="operate('acceptReturn')">登记退货验收</el-button>
 <el-button v-if="availableRefundActions(current.fulfillment).includes('prepareRefund')" :disabled="operating || !mockEnabled" @click="operate('prepareRefund')">准备待执行退款</el-button>
 <el-button v-if="availableRefundActions(current.fulfillment).includes('startMockRefund')" :disabled="operating || !mockEnabled" @click="operate('startMockRefund')">开始本地模拟（持久化处理中）</el-button>
 <el-button v-if="availableRefundActions(current.fulfillment).includes('completeMockRefund')" :disabled="operating || !mockEnabled" @click="operate('completeMockRefund')">登记模拟结果/人工核实结果</el-button>
 <el-button v-if="availableRefundActions(current.fulfillment).includes('timeoutMockRefund')" :disabled="operating || !mockEnabled" @click="operate('timeoutMockRefund')">记录模拟超时（结果未知）</el-button>
 <el-checkbox v-model="manualReconciliation">已人工核实超时结果</el-checkbox>
 </fieldset></div>
 <h3>履约结果（与案件状态独立）</h3>
 <p>退货物流：{{current.fulfillment?.carrier}} {{current.fulfillment?.trackingNo}} · {{current.fulfillment?.logisticsStatus}}</p>
 <p v-if="current.fulfillment?.logisticsNote">人工核实：{{current.fulfillment.logisticsNote}}</p>
 <p v-if="current.fulfillment?.acceptance">验收：{{current.fulfillment.acceptance}} · {{current.fulfillment.acceptanceNote}}</p>
 <p>退款执行：{{current.fulfillment?.refundMode==='MOCK'?'本地模拟（不是资金到账）':'尚无渠道执行记录'}} · {{current.fulfillment?.refundStatus}}</p>
 <p v-if="current.fulfillment?.refundId">原模拟退款单号：{{current.fulfillment.refundId}}；{{current.fulfillment.failureReason}}</p>
 <p v-if="current.fulfillment?.acceptanceEvidence?.length">验收证据：{{current.fulfillment.acceptanceEvidence.join('；')}}</p><details><summary>查看诊断、方案与完整审计记录</summary><h3>诊断与证据</h3><pre>{{pretty(current.diagnosis)}}</pre>
 <h3>方案版本</h3><pre>{{pretty(current.plans)}}</pre>
 <h3>人工任务</h3><pre>{{pretty(current.tasks)}}</pre>
 <h3>审计时间线</h3><el-table :data="current.timeline || []"><el-table-column prop="createdAt" label="时间"/><el-table-column prop="action" label="动作"/><el-table-column prop="actorType" label="角色"/><el-table-column prop="fromState" label="原状态"/><el-table-column prop="toState" label="新状态"/><el-table-column prop="note" label="说明"/></el-table>

 </details></template></el-dialog></section>
</template>
<script setup>
import {getCurrentInstance,onMounted,ref,computed} from 'vue'
import {ElMessageBox} from 'element-plus'
import {caseStates,availableCaseActions,caseCommand,fulfillmentNote,availableRefundActions,refundWorkflowGuide} from '@/utils/caseManagement.mjs'
const {proxy}=getCurrentInstance(),rows=ref([]),state=ref(''),page=ref(1),loading=ref(false),error=ref(''),current=ref(null),open=ref(false),note=ref(''),operating=ref(false)
const labels={approve:'批准进入人工处理',reject:'驳回方案',claim:'领取人工任务',succeed:'记录处理成功',fail:'记录处理失败',retry:'创建重试任务',archive:'归档'}
Object.assign(labels,{returnLogistics:'登记退货物流',acceptReturn:'登记退货验收',returnProgress:'登记物流进度',simulateRefund:'本地模拟退款（不产生资金操作）',prepareRefund:'准备待执行退款',startMockRefund:'开始本地模拟',completeMockRefund:'登记模拟结果',timeoutMockRefund:'记录超时未知'})
const acceptanceEvidence=ref(''),received=ref(false),returnCondition=ref('UNKNOWN');
const fulfillmentType=ref('return_refund'),carrier=ref(''),trackingNo=ref(''),accepted=ref(false),manualReconciliation=ref(false),simulateFailure=ref(false),logisticsStatus=ref('IN_TRANSIT')
const dialogError=ref(''),notice=ref('')
const mockEnabled=computed(()=>current.value?.capabilities?.mockRefundEnabled===true)
const guide=computed(()=>refundWorkflowGuide(current.value || {}))
const hasTracking=computed(()=>!!current.value?.fulfillment?.trackingNo)
const canRegisterTracking=computed(()=>!current.value?.fulfillment?.acceptance && (!hasTracking.value || carrier.value.trim()!==(current.value.fulfillment.carrier || '').trim() || trackingNo.value.trim()!==(current.value.fulfillment.trackingNo || '').trim()))
const endpoint='/aftersalesCase/'
const pretty=v=>JSON.stringify(v,null,2)
async function load(){loading.value=true;error.value='';try{const r=await proxy.Request({url:endpoint+'list',params:{page:page.value,size:20,...(state.value?{state:state.value}:{})}});if(!r)throw new Error();rows.value=r.data}catch{rows.value=[];error.value='案件查询失败，请检查登录权限和订单服务；未用空列表掩盖错误'}finally{loading.value=false}}
async function detail(caseId){dialogError.value='';notice.value='';try{const r=await proxy.Request({url:endpoint+'detail',params:{caseId}});if(!r)throw new Error();current.value=r.data;note.value='';fulfillmentType.value=r.data.requestedType || r.data.fulfillment?.type || 'return_refund';carrier.value=r.data.fulfillment?.carrier || '';trackingNo.value=r.data.fulfillment?.trackingNo || '';received.value=false;accepted.value=false;manualReconciliation.value=false;simulateFailure.value=false;acceptanceEvidence.value='';returnCondition.value='UNKNOWN';open.value=true}catch{error.value='案件详情读取失败，请刷新或检查权限'}}
async function operate(action){
 if(operating.value)return
 operating.value=true;dialogError.value='';notice.value=''
 try{
  const fulfillment=['returnLogistics','returnProgress','acceptReturn','simulateRefund','prepareRefund','startMockRefund','completeMockRefund','timeoutMockRefund'].includes(action)
  if(['prepareRefund','startMockRefund','completeMockRefund','timeoutMockRefund','simulateRefund'].includes(action)&&!mockEnabled.value)throw new Error('本环境未启用模拟退款，不能执行模拟；不会自动调用真实退款渠道。')
  const content=fulfillment?fulfillmentNote(action,{type:fulfillmentType.value,carrier:carrier.value,trackingNo:trackingNo.value,received:received.value,condition:returnCondition.value,accepted:accepted.value,evidenceRefs:acceptanceEvidence.value.trim()?[acceptanceEvidence.value.trim()]:[],simulateFailure:simulateFailure.value,manualReconciliation:manualReconciliation.value,logisticsStatus:logisticsStatus.value,result:note.value}):note.value
  const cmd=caseCommand(current.value,crypto.randomUUID(),content)
  await ElMessageBox.confirm(`${labels[action]}？此操作不会执行真实退款或支付。`,'人工确认',{type:'warning',closeOnClickModal:false})
  const r=await proxy.Request({url:endpoint+action,params:cmd,dataType:'json',showError:false,throwOnError:true})
  if(!r)throw new Error('操作未保存，请核实登录和服务状态后刷新；不要重复提交。')
  current.value=r.data;note.value='';notice.value=labels[action]+'已保存。请按上方当前步骤继续；不代表真实资金到账。';await load()
 }catch(e){if(e!=='cancel'&&e!=='close')dialogError.value=e?.message || '操作未完成，请刷新案件核实服务端结果。'}
 finally{operating.value=false}
}
onMounted(load)
</script>
<style scoped>.cases{padding:16px}.tools{display:flex;gap:12px;margin:16px 0}.case-workbench{padding:16px;background:#fafafa;border:1px solid #ddd;border-radius:8px}.case-workbench .el-alert{margin-bottom:12px}fieldset{margin-top:14px}details{margin-top:20px}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:360px;overflow:auto}</style>
