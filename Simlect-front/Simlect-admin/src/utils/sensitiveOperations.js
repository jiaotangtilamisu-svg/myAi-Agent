// Keep aligned with backend @AdminSensitiveConfirm endpoints.
export const sensitivePaths = new Set([
  '/admin/productInfo/publishReferenceCatalogue',
  '/admin/productInfo/publishPublicCatalogue',
  '/admin/productInfo/prepareCatalogue',
  '/admin/discountCoupon/updateDiscountCouponStatus',
  '/admin/order/bizComment', '/admin/order/delComment', '/admin/order/delivery',
  '/admin/orderInfo/deleteOrderInfoByOrderId', '/admin/orderInfo/updateOrderInfoByOrderId',
  '/admin/productInfo/deleteProduct', '/admin/productInfo/deleteProductInfoByProductId',
  '/admin/productInfo/updateProduct', '/admin/productInfo/updateProductInfoByProductId',
  '/admin/productInfo/updateProductStatus', '/admin/productInfo/updateSkuStock',
  '/admin/productPropertyValue/deleteProductPropertyValueByProductIdAndPropertyValueId',
  '/admin/productSku/deleteProductSkuByProductIdAndPropertyValueIdHash',
  '/admin/sensitiveWord/delete', '/admin/sensitiveWord/save',
  '/admin/sysCategory/delCategory', '/admin/sysCategory/delProductProperty',
  '/admin/user/changeStatus', '/admin/userInfo/deleteUserInfoByEmail',
  '/admin/userInfo/deleteUserInfoByNickName', '/admin/userInfo/deleteUserInfoByUserId',
])

export function adminOperationPath(url) {
  const path = String(url || '').split('?')[0].replace(/^\/(?:admin-api|api)(?=\/)/, '')
  return path.startsWith('/admin/') ? path : `/admin${path.startsWith('/') ? '' : '/'}${path}`
}

export async function confirmationForRequest(url, token, prompt) {
  if (typeof token === 'string' && token) return token
  const path = adminOperationPath(url)
  if (!sensitivePaths.has(path)) return undefined
  return prompt('此操作需要二次确认，请输入管理员密码', path)
}
