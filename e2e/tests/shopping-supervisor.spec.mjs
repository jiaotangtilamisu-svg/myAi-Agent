import { test, expect } from '@playwright/test';
import { c, database, openChat, send, reportOf } from '../lib/business.mjs';

function assertFacts(result, truth, min=0,max=Infinity) {
 expect(Array.isArray(result.recommendations)).toBe(true);
 for(const product of result.recommendations){
  expect(product.queryTime).toBeTruthy();
  for(const sku of product.skus){
   const stored=truth.skuTruth.find(row=>row.productId===product.productId&&row.skuId===sku.sku_id);
   expect(stored,'SKU must belong to exactly this product').toBeTruthy();
   expect(Number(sku.price)).toBe(Number(stored.price));
   expect(Number(sku.price)).toBeGreaterThanOrEqual(min);expect(Number(sku.price)).toBeLessThanOrEqual(max);
   const stock=truth.stockTruth.find(row=>row.productId===product.productId&&row.skuId===sku.sku_id);
   if(stock){expect(sku.stock).toBe(stock.stock);expect(sku.stock_query_status).toBe('SUCCESS');}
   else {expect(sku.stock).toBeNull();expect(sku.stock_query_status).not.toBe('SUCCESS');}
  }
 }
}
test('真实浏览器导购：三星/Apple、上下限、同SKU价格库存、多轮修改和双商品比较',async()=>{
 await openChat('shopping');
 const rows=[
  {text:'重新选，推荐5000元以上三星手机，256GB，有现货',ids:['DEMO34S1'],min:5000,max:Infinity},
  {text:'改成5000元以内苹果手机，256GB，有现货',ids:['DEMO34A2'],min:0,max:5000},
  {text:'重新选，推荐两款手机',count:2,min:0,max:Infinity}
 ];
 for(let i=0;i<rows.length;i++){
  const query=rows[i]; await send(query.text);
  const truth=database('shopping-'+i);const message=truth.messages.at(-1);
  expect(message.userMessage).toBe(query.text);expect(message.status).toBe(2);
  const report=reportOf(message);assertFacts(report,truth,query.min,query.max);
  if(query.ids)expect(report.recommendations.map(p=>p.productId)).toEqual(query.ids);
  if(query.count)expect(report.recommendations).toHaveLength(query.count);
 }
 await send('比较第一款和第二款');
 const compared=database('shopping-compared');const report=reportOf(compared.messages.at(-1));
 expect(report.isComparison).toBe(true);expect(report.comparison).toHaveLength(2);
 expect(new Set(report.comparison.map(row=>row.productId)).size).toBe(2);
 await c('screenshot','shop',{name:'16-shopping-two-products-compared'});
 await send('重新选，推荐有现货的茶杯');
 const noStock=database('shopping-no-stock');expect(reportOf(noStock.messages.at(-1)).recommendations).toHaveLength(0);
 await c('screenshot','shop',{name:'17-zero-stock-no-fabricated-recommendation'});
});

test('Supervisor真实双Agent执行并持久化各自证据，不将路由描述当成执行',async()=>{
 await openChat('supervisor');
 const text='查询现有售后政策，另外推荐5000元以内的手机';await send(text);
 const truth=database('supervisor-composite');const message=truth.messages.at(-1);
 expect(message.userMessage).toBe(text);expect(message.status).toBe(2);
 const report=reportOf(message);
 expect(report.plan.tasks.map(task=>task.agent).sort()).toEqual(['aftersales','shopping']);
 expect(Object.keys(report.results).sort()).toEqual(['aftersales','shopping']);
 expect(report.results.aftersales.status).toBe('SUCCESS');expect(report.results.shopping.status).toBe('SUCCESS');
 const shopping=report.results.shopping.data.shopping;
 assertFacts(shopping,truth,0,5000);expect(shopping.recommendations.length).toBeGreaterThan(0);
 const policy=report.results.aftersales.data.policy;
 expect(policy.status).toBe('SUCCESS');expect(policy.hits.length).toBeGreaterThan(0);
 for(const hit of policy.hits){
  expect(hit.documentId).toBe('f85d1c36-053a-430b-a05f-e9ce88810e99');expect(hit.chunkId).toBeTruthy();
  // source is the provenance description; originalUrl is the authoritative URL.
  expect(hit.source).toContain('司法部');expect(hit.revision).toBe(1);
  expect(new URL(hit.originalUrl).protocol).toBe('https:');
  expect(new URL(hit.originalUrl).hostname).toBe('xzfg.moj.gov.cn');
 }
 await c('screenshot','shop',{name:'18-supervisor-two-agent-results'});
 await c('reload','shop');
 await c('click','shop',{locator:{role:'button',name:'智能客服',nth:0}});
 const restored=await c('waitText','shop',{text});
 expect(restored.text).toContain(text);
 expect(database('supervisor-refresh').messages.find(row=>row.messageId===message.messageId).bizData).toBe(message.bizData);
 await c('screenshot','shop',{name:'19-supervisor-refresh-persisted'});
});
