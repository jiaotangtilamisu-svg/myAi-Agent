/** Describe transport failures without exposing server payloads or disguising them as success. */
export function transportErrorMessage(error: {code?: string; response?: {status?: number}; config?: {url?: string}}): string {
  const url = (error.config?.url || '').split('?')[0];
  const service = /(?:^|\/)productCart\//.test(url) ? '购物车服务'
    : /(?:^|\/)discountCoupon\//.test(url) ? '优惠券服务'
    : /(?:^|\/)userMember\//.test(url) ? '会员服务'
    : /(?:^|\/)order\//.test(url) ? '订单服务'
    : /(?:^|\/)(?:pay|payTrade)\//.test(url) ? '支付服务'
    : /(?:^|\/)search\//.test(url) ? '搜索服务'
    : /(?:^|\/)product\//.test(url) ? '商品服务'
    : /(?:^|\/)account\//.test(url) ? '账号服务'
    : /(?:^|\/)agent\//.test(url) ? '智能客服服务' : '服务';
  if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') return `${service}请求超时，请稍后重试`;
  const status = error.response?.status;
  if (status === 503) return `${service}暂不可用，请稍后重试`;
  if (status === 502 || status === 504) return `${service}连接异常，请稍后重试`;
  if (status === 429) return '请求过于频繁，请稍后重试';
  if (status && status >= 500) return `${service}处理异常，请稍后重试`;
  if (status === 403) return '当前操作无权限，请核实登录状态';
  if (status === 404) return '请求的接口不存在，请刷新页面后重试';
  return '无法连接服务器，请检查网络或服务运行状态';
}
