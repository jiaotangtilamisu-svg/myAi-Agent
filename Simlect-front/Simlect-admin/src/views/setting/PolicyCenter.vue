<template>
  <section class="policy-center">
    <h2>售后政策管理中心</h2>
    <el-alert title="正式知识库仅接收人工审核并发布的有效政策。行业参考不是商城规则；平台规则须明确标注为演示规则。" type="warning" :closable="false" />
    <p>索引长时间未就绪时，请检查<router-link to="/data/ragSyncFailure">RAG同步失败记录</router-link>，核实原因后人工重试向量化。</p>
    <div class="toolbar">
      <el-select v-model="filters.category" clearable placeholder="全部类别" style="width:260px"><el-option v-for="(v,k) in categories" :key="k" :label="v" :value="k" /></el-select>
      <el-select v-model="filters.state" clearable placeholder="全部状态" style="width:140px"><el-option v-for="(v,k) in states" :key="k" :label="v" :value="k" /></el-select>
      <el-button @click="page=1;load()">查询</el-button><el-button type="primary" @click="edit()">上传政策草稿</el-button>
    </div>
    <el-table :data="rows" border>
      <el-table-column prop="title" label="政策文档" min-width="200" />
      <el-table-column label="分类" min-width="190"><template #default="{row}">{{ categories[row.category] || '未分类' }}</template></el-table-column>
      <el-table-column prop="revision" label="版本" width="70" />
      <el-table-column label="状态" width="110"><template #default="{row}">{{ states[row.state] || row.state }}</template></el-table-column>
      <el-table-column label="索引" width="140"><template #default="{row}">{{ row.indexState }} / v{{ row.indexedRevision }}</template></el-table-column>
      <el-table-column label="有效期（UTC）" min-width="210"><template #default="{row}">{{ row.effectiveFrom || '未设置' }} 至 {{ row.effectiveUntil || '长期' }}</template></el-table-column>
      <el-table-column label="操作" min-width="290"><template #default="{row}">
        <el-button link @click="detail(row)">条款与历史</el-button>
        <el-button v-if="!['RETIRED','DELETED'].includes(row.state)" link @click="edit(row)">新版本/元数据</el-button>
        <el-button v-for="action in availableActions(row)" :key="action" link @click="operate(row,action)">{{ actionNames[action] }}</el-button>
      </template></el-table-column>
    </el-table>
    <div class="toolbar"><el-button :disabled="page===1" @click="page--;load()">上一页</el-button><span>第{{ page }}页</span><el-button :disabled="rows.length<20" @click="page++;load()">下一页</el-button></div>
    <el-dialog v-model="showEditor" title="保存政策草稿（不会自动审核或发布）" width="720px">
      <el-form label-width="150px">
        <el-form-item label="文档名称"><el-input v-model="form.title" :disabled="!!form.documentId && !file" maxlength="200" /></el-form-item>
        <el-form-item label="可追溯来源"><el-input v-model="form.source" :disabled="!!form.documentId && !file" maxlength="1000" placeholder="平台演示规则需明确标注；不要填写密钥" /></el-form-item>
        <el-form-item label="原始文档"><input type="file" accept=".pdf,.docx,.txt" @change="file=$event.target.files[0]" /><small>PDF、DOCX、TXT，最多10MiB；不支持旧版.doc。更新元数据可不选文件。</small></el-form-item>
        <el-form-item label="政策分类"><el-select v-model="form.category"><el-option v-for="(v,k) in categories" :key="k" :label="v" :value="k" /></el-select></el-form-item>
        <el-form-item label="发布机构"><el-input v-model="form.issuer" maxlength="200" /></el-form-item>
        <el-form-item label="原始HTTPS网址"><el-input v-model="form.originalUrl" maxlength="1000" /></el-form-item>
        <el-form-item label="原始发布日期"><el-date-picker v-model="form.publishedOn" type="date" value-format="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="来源有效状态"><el-select v-model="form.sourceStatus"><el-option label="未核实" value="UNVERIFIED"/><el-option label="已人工核实有效" value="VALID"/><el-option label="无效" value="INVALID"/></el-select></el-form-item>
        <el-form-item label="生效时间"><el-date-picker v-model="startTime" type="datetime" placeholder="本地时间，提交转换UTC" /></el-form-item>
        <el-form-item label="失效时间"><el-date-picker v-model="endTime" type="datetime" clearable placeholder="留空长期有效" /></el-form-item>
      </el-form>
      <el-alert v-if="form.documentId" title="修改正文或元数据会生成新版本并撤销审核与发布资格，必须重新审核。" :closable="false" />
      <template #footer><el-button @click="showEditor=false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存草稿</el-button></template>
    </el-dialog>
    <el-dialog v-model="showDetail" title="原始条款、版本与审计" width="80%">
      <template v-if="current.document">
        <p>{{ current.document.title }} — {{ categories[current.document.category] }}</p>
        <p>来源：{{ current.document.source }}；机构：{{ current.document.issuer || '未知' }}；原始网址：{{ current.document.originalUrl || '未提供' }}</p>
        <p>UTC有效期：{{ current.document.effectiveFrom }} 至 {{ current.document.effectiveUntil || '长期' }}；来源状态：{{ current.document.sourceStatus }}</p>
        <el-select v-model="selectedVersion" @change="loadVersion"><el-option v-for="v in current.versions" :key="v" :label="`版本 ${v}`" :value="v"/></el-select>
        <a :href="originalUrl" target="_blank" rel="noopener">下载该版本原始文档</a>
        <p v-if="versionMeta">该版本来源：{{ versionMeta.source }}；机构：{{ versionMeta.issuer || '未知' }}；原始网址：{{ versionMeta.originalUrl || '未提供' }}</p>
        <article v-for="chunk in shownChunks" :key="chunk.chunkId"><h4>{{ chunk.section }} / {{ chunk.page ? `第${chunk.page}页` : '原文条款（无固定页码）' }}</h4><pre>{{ chunk.text }}</pre></article>
        <h3>操作审计（最近200条，操作者为服务端生成的匿名标识）</h3>
        <el-table :data="current.audit"><el-table-column prop="created_at" label="时间"/><el-table-column prop="revision" label="版本"/><el-table-column prop="action" label="操作"/><el-table-column prop="from_state" label="原状态"/><el-table-column prop="to_state" label="新状态"/><el-table-column prop="actor" label="操作者" min-width="230"/></el-table>
      </template>
    </el-dialog>
  </section>
</template>
<script setup>
import { ref, reactive, computed, getCurrentInstance, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { categories, states, availableActions, utcValue } from '@/utils/policyManagement.mjs'
const { proxy }=getCurrentInstance()
const endpoint='/rag/knowledge/'
const rows=ref([]), page=ref(1), filters=reactive({category:'',state:''}), showEditor=ref(false), showDetail=ref(false), saving=ref(false)
const form=reactive({}), file=ref(), startTime=ref(), endTime=ref(), current=ref({}), selectedVersion=ref(), shownChunks=ref([]), versionMeta=ref()
const actionNames={submit:'提交审核',approve:'审核通过',reject:'驳回',publish:'人工确认发布',disable:'停用',enable:'重新启用',reindex:'重试向量化',retire:'归档'}
const originalUrl=computed(()=>`${import.meta.env.PROD?'/admin-api':'/api'}${endpoint}original?documentId=${encodeURIComponent(current.value.document?.documentId || '')}&revision=${selectedVersion.value || 1}`)
async function request(action,params){return proxy.Request({url:endpoint+action,params})}
async function load(){const r=await request('list',{page:page.value,size:20,...filters});if(r) rows.value=r.data}
function edit(row){Object.keys(form).forEach(k=>delete form[k]);Object.assign(form,row || {title:'',source:'Simlect平台自有演示规则（未审核）',category:'PLATFORM_DEMO',issuer:'Simlect',originalUrl:'',publishedOn:'',sourceStatus:'UNVERIFIED'});file.value=undefined;startTime.value=row?.effectiveFrom ? new Date(row.effectiveFrom+'Z') : undefined;endTime.value=row?.effectiveUntil ? new Date(row.effectiveUntil+'Z') : undefined;showEditor.value=true}
async function save(){
 if(!form.title || !form.source || !startTime.value){ElMessage.error('请填写文档名称、来源和生效时间');return}
 if(!form.documentId && !file.value){ElMessage.error('请选择原始文档');return}
 if(file.value && file.value.size>10*1024*1024){ElMessage.error('文档不能超过10MiB');return}
 saving.value=true
 try{const data={...form,effectiveFrom:utcValue(startTime.value),effectiveUntil:utcValue(endTime.value),publishedOn:form.publishedOn || ''};if(file.value){data.file=file.value;data.expectedRevision=form.revision ?? ''}else data.revision=form.revision
 const r=await request(file.value?'import':'metadata',data);if(r){showEditor.value=false;await load()}}
 finally{saving.value=false}
}
async function operate(row,action){try{await ElMessageBox.confirm(`${actionNames[action]}「${row.title}」版本${row.revision}？发布仅影响知识检索，不执行退款。行业参考不得作为商城规则。`,'人工操作确认',{type:'warning'})}catch{return}
 const name=action==='publish'?'publish':action==='reindex'?'reindex':action==='retire'?'delete':'transition'
 const r=await request(name,{documentId:row.documentId,revision:row.revision,action,confirmedPolicy:action==='publish'});if(r) await load()
}
async function detail(row){const r=await request('detail',{documentId:row.documentId});if(r){current.value=r.data;selectedVersion.value=row.revision;shownChunks.value=r.data.chunks;versionMeta.value=r.data.document;showDetail.value=true}}
async function loadVersion(){const r=await request('version',{documentId:current.value.document.documentId,revision:selectedVersion.value});if(r){shownChunks.value=r.data.chunks;versionMeta.value=r.data.metadata}}
onMounted(load)
</script>
<style scoped>
.policy-center{padding:12px}.toolbar{display:flex;gap:12px;align-items:center;margin:16px 0;flex-wrap:wrap}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f5f5;padding:12px}small{color:#666}a{margin-left:16px}article{margin-top:12px}
</style>
