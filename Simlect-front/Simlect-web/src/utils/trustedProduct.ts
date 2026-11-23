/** Nullable read facts; never substitute another SKU's price or invented stock. */
export function knownMoney(value: unknown): number | null {
  if (typeof value !== 'number' && typeof value !== 'string') return null;
  if (typeof value === 'string' && !/^[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value.trim())) return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}
export function priceText(value: unknown): string {
  const number = knownMoney(value);
  return number == null ? '价格未知' : number.toFixed(2);
}
export function skuPrice(sku: Record<string, any> | null | undefined, product?: Record<string, any> | null): number | null {
  return knownMoney(sku?.propertyValueIdHash || sku?.propertyValueIds ? sku.price : product?.minPrice);
}
export function knownStock(sku: Record<string, any> | null | undefined): number | null {
  return sku && (!sku.stockQueryStatus || sku.stockQueryStatus === 'SUCCESS') && Number.isInteger(sku.stock) && sku.stock >= 0 ? sku.stock : null;
}
export function stockText(sku: Record<string, any> | null | undefined): string {
  const count=knownStock(sku);
  return count == null ? sku?.stockQueryStatus === 'UNAVAILABLE' ? '库存服务不可用' : '未知' : String(count);
}
export function purchasableSku(sku: Record<string, any> | null | undefined): boolean {
  const count=knownStock(sku);
  return !!sku?.propertyValueIds && knownMoney(sku.price) != null && count != null && count > 0;
}
