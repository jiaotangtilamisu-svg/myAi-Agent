<template>
  <section>
    <h2>公开资料与商品发布</h2>
    <el-alert title="商品名称和图片来自ABO，人民币售价由本商城自主设定。旧演示商品仅下架保留；不创建库存、不调用付费模型。" :closable="false" type="info" />
    <p v-if="error" role="alert">{{error}}</p>
    <el-button @click="load">刷新批次</el-button>
    <el-button @click="preview">预览商城商品</el-button>
    <el-button @click="previewReady">预览中文商品与库存</el-button>
    <el-button @click="previewReference">预览参考站完整商品目录</el-button>
    <template v-if="referencePlan">
      <h3>参考站商品目录与分类对齐</h3>
      <p>{{referencePlan.products.length}}件商品，保留参考站的商品名称、实际展示售价及SKU。9个一级分类；首页与详情使用对应商品图片。旧ABO商品仅下架，订单、SKU及库存记录保留。</p>
      <p>价格来自参考站公开页面快照；初始化的本地库存用于本机体验，不代表供应商实时库存。不调用模型或Embedding。</p>
      <el-table :data="referencePlan.products.slice(0,8).map(p=>p.productInfo)"><el-table-column prop="productName" label="商品名称" min-width="260"/><el-table-column prop="minPrice" label="参考站售价（元）"/></el-table>
      <el-button type="primary" :loading="referenceRunning" @click="publishReference">导入参考站商品、分类、SKU与本地库存</el-button>
      <p v-if="referenceState" role="status">{{referenceState.status}}：{{referenceState.processed}} / {{referenceState.total}}，阶段：{{referenceState.phase}} {{referenceState.error||''}}</p>
    </template>
    <template v-if="readyPlan">
      <h3>中文商品、库存和搜索修复</h3>
      <p>100件商品改为中文名称；为尚无记录的SKU配置手机壳100件、饮水杯和耳机50件的本地库存；同步商品搜索，不调用模型或向量化。</p>
      <el-table :data="readyPlan.products.slice(0,10)"><el-table-column prop="productName" label="中文商品名" min-width="250"/><el-table-column prop="specification" label="规格"/><el-table-column prop="initialStock" label="初始本地库存"/></el-table>
      <el-button type="primary" :loading="preparing" @click="prepareReady">应用中文商品、库存和搜索修复</el-button>
      <p v-if="readyResult" role="status">{{readyResult}}</p>
    </template>
    <template v-if="plan">
      <h3>商城商品 {{plan.products.length}} 件</h3>
      <p>{{plan.notice}}</p>
      <el-table :data="plan.products.slice(0,10)">
        <el-table-column label="商品图片" width="100"><template #default="{row}"><img :src="'/api/file/getResource?sourceName='+row.cover" style="width:72px;height:72px;object-fit:contain" /></template></el-table-column>
        <el-table-column prop="productName" label="名称" min-width="200" />
        <el-table-column prop="price" label="本商城售价（元）" />
        <el-table-column prop="specification" label="规格" />
      </el-table>
      <el-button type="primary" :loading="publishing" :disabled="published" @click="publish">{{published?'商品已发布':'发布100件商品并下架旧演示商品'}}</el-button>
      <p v-if="result" role="status">{{result}}</p>
    </template>
    <h3>来源批次</h3>
    <el-table :data="rows"><el-table-column prop="batchId" label="批次" min-width="240"/><el-table-column prop="dataset" label="来源" min-width="180"/><el-table-column prop="sourceVersion" label="版本"/><el-table-column prop="status" label="状态"/><el-table-column prop="records" label="记录数"/><el-table-column prop="createdAt" label="导入时间（UTC）"/></el-table>
  </section>
</template>
<script setup>
import {getCurrentInstance,onMounted,onUnmounted,ref} from 'vue'
const {proxy}=getCurrentInstance(),rows=ref([]),error=ref(''),plan=ref(null),publishing=ref(false),published=ref(false),result=ref('')
const readyPlan=ref(null),preparing=ref(false),readyResult=ref('')
const referencePlan=ref(null),referenceState=ref(null),referenceRunning=ref(false)
let referenceTimer=null
async function previewReference(){const r=await proxy.Request({url:'/productInfo/previewReferenceCatalogue',params:{},timeout:30000});if(r)referencePlan.value=r.data}
async function checkReference(){const r=await proxy.Request({url:'/productInfo/referenceCatalogueStatus',params:{},showLoading:false});if(!r)return;referenceState.value=r.data;referenceRunning.value=r.data.status==='RUNNING';if(referenceRunning.value)referenceTimer=setTimeout(checkReference,2500)}
async function publishReference(){if(!referencePlan.value||referenceRunning.value)return;const r=await proxy.Request({url:'/productInfo/publishReferenceCatalogue',params:{planId:referencePlan.value.planId},timeout:30000});if(r){referenceRunning.value=true;await checkReference()}}
onUnmounted(()=>clearTimeout(referenceTimer))
async function previewReady(){const r=await proxy.Request({url:'/productInfo/previewCatalogueReadiness',params:{}});if(r)readyPlan.value=r.data}
async function prepareReady(){if(preparing.value||!readyPlan.value)return;preparing.value=true;try{const r=await proxy.Request({url:'/productInfo/prepareCatalogue',params:{planId:readyPlan.value.planId},timeout:90000});if(r)readyResult.value='中文商品、库存与搜索已就绪，重复执行不会覆盖已有库存。'}finally{preparing.value=false}}
async function load(){error.value='';const r=await proxy.Request({url:'/productInfo/publicBatches',params:{}});if(r)rows.value=r.data;else error.value='批次读取失败，请检查管理员权限和商品服务'}
async function preview(){const r=await proxy.Request({url:'/productInfo/previewPublicCatalogue',params:{}});if(r)plan.value=r.data}
async function publish(){if(!plan.value||publishing.value)return;publishing.value=true;try{const r=await proxy.Request({url:'/productInfo/publishPublicCatalogue',params:{planId:plan.value.planId}});if(r){published.value=true;result.value=`已发布${r.data.products}件商品；请刷新商城首页。`;await load()}}finally{publishing.value=false}}
onMounted(load)
</script>
