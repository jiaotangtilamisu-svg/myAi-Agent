export function dataOriginLabel(value: unknown): string {
  if (!value || typeof value !== 'object') return '业务来源未登记';
  const origin = value as Record<string, unknown>;
  const type = String(origin.sourceType ?? origin.source_type ?? '');
  const labels: Record<string, string> = {
    PUBLIC_DATASET: '公开历史数据 · 非当前交易',
    SYNTHETIC: '合成测试数据', MANUAL: '手工维护资料', LIVE_API: '实时业务来源'
  };
  const fields = (origin.fieldSources ?? origin.field_sources ?? {}) as Record<string, unknown>;
  const synthetic = Object.values(fields).includes('SYNTHETIC');
  return (labels[type] ?? '业务来源未登记') + (synthetic && type !== 'SYNTHETIC' ? ' · 含合成字段' : '');
}
export function productOriginLabel(product: Record<string, any>): string {
 const origin=product.dataProvenance || {};
 const source=origin.sourceType || origin.source_type;
 if(source==='PUBLIC_DATASET')return '公开商品目录资料；价格、库存以本商城查询为准，不代表来源商家实时数据';
 if(product.dataClass==='LOCAL_STORE')return '当前商城目录；价格和库存为本地配置';
 if(product.dataClass==='DEMO')return '本地演示商品';
 if(product.dataClass==='TEST')return '隔离测试商品';
 if(product.dataClass==='REAL')return '已核实业务来源';
 return '商品资料来源待核实';
}
