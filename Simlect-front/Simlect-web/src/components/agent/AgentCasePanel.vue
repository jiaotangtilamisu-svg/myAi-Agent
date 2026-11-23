<template>
 <section aria-label="售后申请与处理进度">
  <p>售后申请与处理进度</p>
  <el-button v-if="eligible && !current" :loading="busy" @click="create">生成待确认的售后方案</el-button>
  <el-button :loading="busy" @click="load">查询我的售后申请</el-button>
  <p v-if="error" role="alert">{{error}}</p>
  <p v-if="!busy && !error && !rows.length && !current">{{orderId?'本订单暂无售后申请记录。':'当前账号暂无售后申请记录。'}}售后案件与支付渠道退款记录分别查询。</p>
  <div v-for="r in rows" :key="r.caseId" role="group" :aria-label="'售后申请 '+r.caseId" :data-case-id="r.caseId">
   <p>编号：{{r.caseId}}</p>
   <p>订单 {{r.orderId}} · {{labels[r.state] || '待核实'}} · 方案版本 {{r.planVersion}}</p>
   <el-button @click="detail(r.caseId)">查看方案与进度</el-button>
  </div>
  <template v-if="current">
   <p>{{current.state==='AWAITING_USER'?'方案草稿编号':'申请编号'}}：{{current.caseId}}</p>
   <p>申请原因：{{current.applicationReason || '尚未确认提交'}}</p>
   <ul v-if="current.applicationMaterials?.length"><li v-for="(material,i) in current.applicationMaterials" :key="i">申请材料说明：{{material}}</li></ul>
   <p>方案 {{current.planVersion}}：{{labels[current.state] || '待核实'}}</p>
   <p role="status">{{caseGuidance(current.state)}}</p>
   <el-button :loading="busy" @click="detail(current.caseId)">刷新当前申请进度</el-button>
   <p v-if="current.requestedType">申请类型：{{current.requestedType==='refund'?'仅退款':current.requestedType==='exchange'?'人工换货':'退货退款'}}</p>
   <el-button v-if="['AWAITING_USER','ADMIN_REVIEW','REJECTED','MANUAL_PENDING'].includes(current.state)" :disabled="busy" @click="cancelCase">取消此申请/草稿</el-button>
   <ul><li v-for="(action,i) in currentPlan?.actions || []" :key="i">{{action.title}}</li></ul>
   <p v-if="current.risk==='HIGH' && ['AWAITING_USER','ADMIN_REVIEW','REJECTED'].includes(current.state)">本方案需要管理员审核后，由人工处理。</p>
   <details v-if="currentPlan?.policyEvidence?.hits?.length"><summary>方案政策依据与原文</summary><section v-for="h in currentPlan.policyEvidence.hits" :key="h.chunkId"><p>{{h.documentName}} · 版本{{h.revision}} · {{h.source}}</p><blockquote style="white-space:pre-wrap">{{h.text}}</blockquote></section></details>
   <p v-if="['AWAITING_USER','ADMIN_REVIEW','REJECTED'].includes(current.state)">提交后按风险进入管理员审核或人工处理，不代表退款已执行。</p>
   <template v-if="['AWAITING_USER','REJECTED'].includes(current.state)">
   <el-select v-model="requestedType" placeholder="选择申请类型"><el-option label="仅退款" value="refund"/><el-option label="退货退款" value="return_refund"/><el-option label="换货（人工审核）" value="exchange"/></el-select><el-input v-model="supplement" type="textarea" maxlength="1000" placeholder="请填写真实申请原因，供管理员审核"/><el-input v-model="material" type="textarea" maxlength="350" placeholder="可选：描述质量问题、照片证据或沟通凭证（不上传文件）"/><el-button :disabled="busy || !supplement.trim()" @click="amend">保存原因、材料和类型修改</el-button><el-input v-model="secondMaterial" type="textarea" maxlength="350" placeholder="可选：第二项证据说明"/><el-button v-if="current.state==='AWAITING_USER'" :disabled="busy || !supplement.trim()" @click="confirm">确认方案并提交申请</el-button></template>
   <template v-if="current.state==='REJECTED'"><el-button :disabled="busy || !supplement.trim()" @click="amend">保存补充材料并生成待确认方案</el-button></template>
   <section v-if="current.fulfillment" aria-label="退货物流与退款结果">
     <p role="status">{{caseFulfillmentGuidance(current)}}</p>
     <p>退货物流：{{logisticsLabels[current.fulfillment.logisticsStatus] || '尚未登记'}} {{current.fulfillment.carrier}} {{current.fulfillment.trackingNo}}</p>
     <p v-if="current.fulfillment.logisticsNote">物流核实说明：{{current.fulfillment.logisticsNote}}（人工核实记录，并非承运商实时接口）</p>
     <p v-if="current.fulfillment.acceptance">验收{{current.fulfillment.acceptance==='ACCEPTED'?'通过':'未通过'}}：{{current.fulfillment.acceptanceNote}}</p>
     <p v-if="current.fulfillment.refundMode==='MOCK'">本地模拟退款：{{refundLabels[current.fulfillment.refundStatus] || '待核实'}}；模拟单号：{{current.fulfillment.refundId}}。不代表资金到账。</p>
     <p v-if="current.fulfillment.failureReason">失败原因：{{current.fulfillment.failureReason}}</p>
     <template v-if="['MANUAL_PENDING','IN_PROGRESS'].includes(current.state) && current.requestedType==='return_refund' && current.fulfillment.logisticsStatus==='NOT_REGISTERED'">
       <p>仅在审核确认需要退货并取得退货地址后填写；仅退款无需寄回。</p>
       <el-input v-model="carrier" maxlength="80" placeholder="退货物流公司"/><el-input v-model="trackingNo" maxlength="60" placeholder="实际退货运单号"/>
       <el-button :disabled="busy || !carrier.trim() || !/^(?=.*[A-Za-z0-9])[A-Za-z0-9-]{5,60}$/.test(trackingNo)" @click="submitLogistics">确认提交退货物流</el-button>
     </template>
   </section>
   <details><summary>查看完整处理记录</summary><p v-for="(event,i) in current.timeline || []" :key="i">{{event.createdAt}} · {{labels[event.toState] || '处理记录'}} · {{eventNote(event)}}</p></details>
  </template>
 </section>
</template>
<script setup lang="ts">
import {computed,ref,onMounted} from 'vue';
import {confirmAction} from '@/utils/confirm';
import request from '@/api/http';
import {useAuthStore} from '@/stores/auth';
import {readCasesOnce} from '@/utils/caseReads';
import {caseGuidance,caseFulfillmentGuidance,caseOperationError,caseTimelineNote,applicationDraft,applicationPayload} from '@/utils/aftersalesCaseView';
const props=defineProps<{messageId:number;eligible:boolean;suggestedType?:string;orderId?:string}>();
const auth=useAuthStore();
const rows=ref<any[]>([]),current=ref<any>(null),busy=ref(false),error=ref('');
const requestedType=ref(props.suggestedType==='refund'?'refund':props.suggestedType==='exchange'?'exchange':'return_refund');
const supplement=ref(''),carrier=ref(''),trackingNo=ref(''),material=ref(''),secondMaterial=ref('');
const refundLabels:Record<string,string>={PENDING:'待执行',PROCESSING:'处理中',SUCCEEDED:'成功',FAILED:'失败',UNKNOWN:'超时，结果未知',NOT_EXECUTED:'未执行'};
const logisticsLabels:Record<string,string>={NOT_REGISTERED:'尚未登记',REGISTERED:'已登记待核实',IN_TRANSIT:'运输中',DELIVERED:'已送达待验收',EXCEPTION:'运输异常，人工跟进'};
const currentPlan=computed(()=>{try{const p=current.value?.plans?.at(-1);return typeof p?.content==='string'?JSON.parse(p.content):p?.content || null;}catch{return null;}});
const labels:Record<string,string>={AWAITING_USER:'等待本人确认',ADMIN_REVIEW:'待管理员审核',REJECTED:'已驳回',MANUAL_PENDING:'等待人工处理',IN_PROGRESS:'人工处理中',PROCESSING_FAILED:'处理失败，待人工跟进',RESOLVED:'处理已完成',ARCHIVED:'已归档',CANCELLED:'已取消'};
const eventNote=caseTimelineNote;
async function run(fn:()=>Promise<void>){if(busy.value)return;busy.value=true;error.value='';try{await fn()}catch(e){error.value=caseOperationError(e)}finally{busy.value=false}}
async function load(){await run(async()=>{const scope=props.orderId || '';const key=auth.userInfo?.userId?String(auth.userInfo.userId)+'|'+scope:'';const value=await readCasesOnce(key,()=>request.postForm('/order/aftersalesCase/list',{page:1,size:20,...(scope?{orderId:scope}:{})}));if(!Array.isArray(value))throw new Error('申请查询结果不完整');rows.value=value.filter(r=>!scope || r.orderId===scope);if(scope && rows.value.length===1){current.value=await readCasesOnce(key+'|'+rows.value[0].caseId,()=>request.postForm('/order/aftersalesCase/detail',{caseId:rows.value[0].caseId}));const draft=applicationDraft(current.value);supplement.value=draft.reason;requestedType.value=draft.requestedType;[material.value,secondMaterial.value]=draft.materials}})}
async function detail(caseId:string){await run(async()=>{current.value=await request.postForm('/order/aftersalesCase/detail',{caseId});const draft=applicationDraft(current.value);supplement.value=draft.reason;requestedType.value=draft.requestedType;[material.value,secondMaterial.value]=draft.materials})}
async function create(){await run(async()=>{current.value=await request.postForm('/agent/aftersales/cases',{messageId:props.messageId});rows.value=[current.value]})}
async function confirm(){if(!supplement.value.trim())return;await run(async()=>{if(!await confirmAction('确认此售后方案及申请原因并提交人工处理？不会自动退款。',{title:'确认申请'}))return;current.value=await request.post('/order/aftersalesCase/confirm',{caseId:current.value.caseId,expectedVersion:current.value.version,requestId:crypto.randomUUID(),note:applicationPayload(supplement.value,[material.value,secondMaterial.value],requestedType.value)});rows.value=[current.value];supplement.value='';material.value='';secondMaterial.value=''})}
async function submitLogistics(){await run(async()=>{if(!await confirmAction('确认运单真实且已按审核要求寄回？此操作只登记物流，不执行退款。',{title:'登记退货物流'}))return;current.value=await request.post('/order/aftersalesCase/returnLogistics',{caseId:current.value.caseId,expectedVersion:current.value.version,requestId:crypto.randomUUID(),note:JSON.stringify({type:'return_refund',carrier:carrier.value.trim(),trackingNo:trackingNo.value.trim()})});rows.value=[current.value];carrier.value='';trackingNo.value=''})}
async function amend(){await run(async()=>{current.value=await request.post('/order/aftersalesCase/amend',{caseId:current.value.caseId,expectedVersion:current.value.version,requestId:crypto.randomUUID(),note:applicationPayload(supplement.value,[material.value,secondMaterial.value],requestedType.value)});rows.value=[current.value]})}
async function cancelCase(){await run(async()=>{if(!await confirmAction('确认取消此申请或草稿？已处理中请联系人工，不会取消订单或执行资金操作。',{title:'取消售后申请'}))return;current.value=await request.post('/order/aftersalesCase/cancel',{caseId:current.value.caseId,expectedVersion:current.value.version,requestId:crypto.randomUUID(),note:'用户主动取消售后申请'});rows.value=[current.value]})}
onMounted(()=>{void load()});
</script>

