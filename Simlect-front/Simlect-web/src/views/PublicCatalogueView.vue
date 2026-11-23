<template><section class="public-catalogue"><h1>公开商品资料</h1>
<el-alert title="仅供资料展示与研究：这些记录不是商城当前可购买商品，无当前报价或已核实库存，不提供下单入口。" type="warning" :closable="false"/>
<form @submit.prevent="page=1;load()"><el-input v-model="keyword" placeholder="搜索公开商品名称" style="max-width:340px"/><el-button native-type="submit">查询</el-button></form>
<p v-if="error" role="alert">{{error}}</p><p v-else>共{{total}}条公开资料</p>
<div v-loading="loading" class="grid"><article v-for="row in rows" :key="row.sourceId"><h2>{{row.productName}}</h2><p>类别：{{row.category || '未知'}} · 品牌/制造商：{{row.brand || '未知'}}</p><p>{{historicalPriceLabel(row.historicalPrice,row.originalCurrency)}}</p><p>真实当前价格：未知 · 库存：未知 · SKU：无可靠数据</p><p v-if="syntheticDemoPrice(row) !== null">人民币演示价：¥{{syntheticDemoPrice(row)?.toFixed(2)}}（本地合成，仅测试，不是真实售价）</p><p>评价：{{row.reviews ? '见原始来源' : '没有可用评论数据'}}</p><p>来源：公开数据集 · {{row.sourceName}}</p><p>采集时间：{{row.collectedAt}}；资料更新时间：{{row.dataPeriod || '未知'}}</p><a v-if="publicSourceUrl(row.sourceUrl)" :href="publicSourceUrl(row.sourceUrl)" target="_blank" rel="noopener noreferrer">原始资料 {{row.sourceId}}</a><p>许可：{{row.license}}</p></article></div>
<div class="pager"><el-button :disabled="page===1||loading" @click="page--;load()">上一页</el-button><span>第{{page}}页</span><el-button :disabled="page*20>=total||loading" @click="page++;load()">下一页</el-button></div>
<p>ABO资料来自Amazon.com，数据集贡献者Matthieu Guillaumin、Thomas Dideriksen、Kenan Deng、Himanshu Arora、Jasmine Collins、Jitendra Malik。依据<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer">CC BY 4.0</a>使用；本项目仅选取部分记录、选择原有语言字段并进行结构映射，无商业背书。来源不等于商业在售真实性证明，原商城商品与REAL导购准入保持独立。</p>
</section></template>
<script setup lang="ts">
import {ref,onMounted} from 'vue';import request from '@/api/http';import {historicalPriceLabel,publicSourceUrl,syntheticDemoPrice} from '@/utils/publicCatalogue';
const rows=ref<Record<string,any>[]>([]),keyword=ref(''),page=ref(1),total=ref(0),loading=ref(false),error=ref('');
async function load(){loading.value=true;error.value='';try{const r=await request.get('/product/publicCatalogue',{params:{keyword:keyword.value,page:page.value}});rows.value=r.list;total.value=r.totalCount}catch{error.value='公开资料查询失败，请检查商品服务';rows.value=[]}finally{loading.value=false}}
onMounted(load);
</script>
<style scoped>.public-catalogue{box-sizing:border-box;max-width:1200px;margin:24px auto;padding:16px}form,.pager{display:flex;gap:12px;margin:20px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:16px}article{min-width:0;padding:16px;border:1px solid #ddd;border-radius:12px;overflow-wrap:anywhere}h2{font-size:18px}p{line-height:1.8}.public-catalogue :deep(.el-alert__title){white-space:normal;overflow-wrap:anywhere}@media(max-width:1199px){.public-catalogue{width:calc(100vw - 32px);margin:24px 0}}</style>

