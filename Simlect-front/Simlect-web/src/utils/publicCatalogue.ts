export function historicalPriceLabel(value: unknown, currency: unknown): string {
  if (value===null || value===undefined || value==='' || !/^[A-Z]{3}$/.test(String(currency))) return '历史价格未知';
  const amount=Number(value);
  if(!Number.isFinite(amount)||amount<0)return '历史价格未知';
  return `${currency} ${amount.toFixed(2)}（历史采集，非当前售价）`;
}
export function publicSourceUrl(value: unknown): string | undefined {
  try {const url=new URL(String(value));return ['https:','http:'].includes(url.protocol)&&!url.username&&!url.password?url.href:undefined} catch{return undefined}
}
/** Explicitly synthetic display scenario, never changes source price or buying eligibility. */
export function syntheticDemoPrice(row: Record<string,unknown>): number | null {
  if(row.sourceType!=='PUBLIC_DATASET'||row.sourceName!=='Amazon Berkeley Objects'||typeof row.sourceId!=='string')return null;
  const ranges:Record<string,number[]>={CELLULAR_PHONE_CASE:[1990,2990,3990],DRINKING_CUP:[1990,2990,3990],HEADPHONES:[5990,8990,12990]};
  const cents=ranges[String(row.originalProductType)];if(!cents)return null;
  const index=Array.from(row.sourceId).reduce((sum,c)=>sum+c.charCodeAt(0),0)%cents.length;
  return cents[index]!/100;
}
