/** Hide implementation diagnostics in old product replies, without changing saved evidence. */
export function consumerProductCopy(value: string): string {
  return value.split('\n').filter(line=>!/^\s*业务数据来源未登记\s*$/.test(line))
    .map(line=>line.replace(/\bSKU\s+[a-f0-9]{32}\s*/gi,'规格 ')
      .replace(/；来源：Java 商品\/库存服务。/g,'。')).join('\n');
}
