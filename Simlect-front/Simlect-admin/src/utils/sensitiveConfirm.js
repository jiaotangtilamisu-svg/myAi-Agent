import { ElMessageBox } from 'element-plus'
import axios from 'axios'

const ios26MessageBoxOptions = {
  closeOnClickModal: false,
  distinguishCancelAndClose: true,
  autofocus: false,
  center: true,
}

// 敏感操作确认：先向服务端校验密码换取一次性票据，再执行操作
// （票据 5 分钟有效、绑定管理员与目标操作路径、消费即销毁）
async function exchangeConfirmToken(password, targetPath) {
  const base = import.meta.env.PROD ? '/admin-api' : '/api'
  let path = String(targetPath || '').trim()
  path = path.replace(/^\/(?:admin-api|api)(?=\/)/, '')
  if (!path) throw new Error('未指定需要确认的操作')
  if (!path.startsWith('/admin/')) path = `/admin${path.startsWith('/') ? '' : '/'}${path}`
  const res = await axios.post(
    `${base}/account/confirmPassword`,
    new URLSearchParams({ password, targetPath: path }),
    { withCredentials: true, headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'XMLHttpRequest' } },
  )
  if (res.data?.status !== 'success' || !res.data?.data) {
    throw new Error(res.data?.info || '二次确认失败')
  }
  return res.data.data
}

export async function promptAdminConfirmPassword(message = '此操作为敏感操作，请输入管理员密码确认', targetPath = '') {
  const { value } = await ElMessageBox.prompt(message, '安全确认', {
    ...ios26MessageBoxOptions,
    inputType: 'password',
    inputPlaceholder: '管理员密码',
    confirmButtonText: '确认',
    cancelButtonText: '取消',
  })
  if (!value) {
    throw new Error('cancel')
  }
  // 校验密码并换取一次性确认票据（绑定目标操作路径）
  return exchangeConfirmToken(value, targetPath)
}


export const ConfirmSensitive = ({ message, url, okfun, targetPath }) => {
  ElMessageBox.confirm(message, '提示', {
    ...ios26MessageBoxOptions,
    confirmButtonText: '继续',
    cancelButtonText: '取消',
  })
    .then(async () => {
      // 目标操作路径：优先显式 targetPath，否则取调用点传入的接口 url
      const confirmToken = await promptAdminConfirmPassword(message, targetPath || url || '')
      if (okfun) {
        await okfun(confirmToken)
      }
    })
    .catch(() => {})
}

export { ConfirmSensitive as default }
