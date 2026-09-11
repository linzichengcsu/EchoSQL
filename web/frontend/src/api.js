// 后端 REST API 封装（与 web/app.py 的接口一一对应）
const JSON_HEADERS = { 'Content-Type': 'application/json' }

async function http(url, options) {
  const resp = await fetch(url, options)
  const data = await resp.json().catch(() => ({}))
  return { httpOk: resp.ok, status: resp.status, data }
}

/** POST /api/sql 执行 SQL；返回 {httpOk, status, data} */
export function runSql(sql) {
  return http('/api/sql', { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ sql }) })
}

/** GET /api/tables 列出全部表及结构 */
export function fetchTables() {
  return http('/api/tables')
}

/** GET /api/stats 页缓存命中率等运行统计 */
export function fetchStats() {
  return http('/api/stats')
}

/** GET /api/health 健康检查与环境版本 */
export function fetchHealth() {
  return http('/api/health')
}

export default { runSql, fetchTables, fetchStats, fetchHealth }
