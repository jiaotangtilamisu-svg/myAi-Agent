export function firstCover(value) {
  return typeof value === 'string' ? value.split(',').map(v => v.trim()).find(Boolean) || '' : ''
}
export function coverList(value) { return typeof value === 'string' ? value.split(',').map(v => v.trim()).filter(Boolean) : [] }
export function skuReadValues(row) { return {price: row.price ?? null, stock: row.stock ?? null, stockQueryStatus: row.stockQueryStatus || 'UNKNOWN', priceStatus: row.priceStatus || (row.price == null ? 'UNKNOWN' : 'KNOWN'), productId: row.productId} }
export function displayAmount(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value.toFixed(2) : '未知'
}
export function displayStock(value, status) {
  return status === 'UNAVAILABLE' ? '库存服务不可用' : Number.isInteger(value) && value >= 0 ? String(value) : '库存未知'
}
export function priceRangeLabel(row) {
  const min=displayAmount(row?.minPrice),max=displayAmount(row?.maxPrice)
  return min==='未知'||max==='未知'?'价格未知':min===max?`¥${min}`:`¥${min}~${max}`
}
