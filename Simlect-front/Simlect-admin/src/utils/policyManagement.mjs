export const categories = { LAW: '官方法律法规', INDUSTRY_REFERENCE: '行业对标参考（非商城规则）', PLATFORM_DEMO: 'Simlect平台自有演示规则' }
export const states = { DRAFT: '草稿', PENDING_REVIEW: '待审核', PUBLISHED: '已发布', DISABLED: '已停用', RETIRED: '已归档' }
export function availableActions(doc) {
  if (doc.state === 'DRAFT') return ['submit']
  if (doc.state === 'PENDING_REVIEW') return doc.approved && doc.reviewedRevision === doc.revision ? ['publish', 'reject'] : ['approve', 'reject']
  if (doc.state === 'PUBLISHED') return ['disable', 'reindex', 'retire']
  if (doc.state === 'DISABLED') return ['enable', 'retire']
  return []
}
export function utcValue(value) { return value ? new Date(value).toISOString() : '' }
