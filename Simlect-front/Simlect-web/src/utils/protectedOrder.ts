/** Keep a denied/failed read explicit and prevent stale data or hook rejections. */
export async function loadProtectedOrder<T>(read: () => Promise<T | null>, kind: '订单' | '物流'):
  Promise<{data: T | null; error: string}> {
  try { return {data: (await read()) || null, error: ''}; }
  catch (failure) {
    const e = failure as {info?: string; code?: string; response?: {status?: number}} | null;
    const denied = e?.response?.status === 403 || /不存在|无权|权限|不属于/.test(e?.info || '');
    return {data: null, error: denied ? `${kind}不存在或无权查看`
      : e?.code === 'ECONNABORTED' || e?.code === 'ETIMEDOUT' ? `${kind}查询超时，请稍后重试`
      : `${kind}查询暂时不可用，请稍后重试`};
  }
}
