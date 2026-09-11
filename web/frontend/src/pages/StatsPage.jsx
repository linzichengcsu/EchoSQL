import { useCallback, useEffect, useState } from 'react'
import { Alert, App as AntApp, Button, Card, Col, Progress, Row, Statistic, Tag } from 'antd'
import {
  ReloadOutlined,
  AimOutlined,
  DatabaseOutlined,
  FireOutlined,
  HddOutlined,
  SwapOutlined,
  TableOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { fetchStats } from '../api'
import ideColors from '../theme'
import PageHeader from '../components/PageHeader'

const MONO = "Consolas, 'Cascadia Code', 'JetBrains Mono', 'Courier New', monospace"

export default function StatsPage() {
  const { message } = AntApp.useApp()
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await fetchStats()
      setStats(data)
    } catch {
      setError('加载统计失败，请确认后端服务已启动')
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const hitRate = stats ? Math.round((stats.hit_rate ?? 0) * 100) : 0

  const items = [
    { title: '表数量', value: stats?.tables ?? '–', icon: <TableOutlined />, color: ideColors.blue },
    { title: '缓存容量', value: stats?.capacity ?? '–', suffix: '页', icon: <DatabaseOutlined />, color: ideColors.green },
    { title: '已缓存页', value: stats?.cached ?? '–', suffix: '页', icon: <HddOutlined />, color: ideColors.yellow },
    { title: '命中次数', value: stats?.hits ?? '–', icon: <AimOutlined />, color: ideColors.green },
    { title: '未命中', value: stats?.misses ?? '–', icon: <FireOutlined />, color: ideColors.orange },
    { title: '驱逐次数', value: stats?.evictions ?? '–', icon: <SwapOutlined />, color: ideColors.purple },
    { title: '脏页数', value: stats?.dirty_pages?.length ?? '–', icon: <WarningOutlined />, color: ideColors.red },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <PageHeader
        title="运行统计"
        subtitle="页缓存（Buffer Pool）命中率与替换统计，贯通存储层 FR-2.2"
        extra={
          <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={load}>
            刷新
          </Button>
        }
      />
      <div style={{ padding: 12, overflow: 'auto', flex: 1 }}>
        {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}
        <Row gutter={[12, 12]}>
          {/* 命中率 */}
          <Col xs={24} md={8} lg={6}>
            <Card size="small" style={{ height: '100%' }}>
              <Statistic
                title="缓存命中率"
                value={stats ? hitRate : '–'}
                suffix="%"
                prefix={<AimOutlined style={{ color: ideColors.accent }} />}
              />
              <Progress
                type="circle"
                size={110}
                percent={hitRate}
                strokeColor={ideColors.green}
                trailColor={ideColors.bgElevated}
                format={(p) => `${p}%`}
                style={{ marginTop: 8 }}
              />
              <div style={{ marginTop: 8 }}>
                替换策略：
                <Tag color="blue" style={{ fontFamily: MONO, marginLeft: 4 }}>
                  {stats?.policy ?? '–'}
                </Tag>
              </div>
            </Card>
          </Col>
          {/* 各统计项 */}
          {items.map((item) => (
            <Col xs={24} sm={12} md={8} lg={6} key={item.title}>
              <Card size="small" style={{ height: '100%' }}>
                <Statistic
                  title={item.title}
                  value={item.value}
                  suffix={item.suffix}
                  prefix={<span style={{ color: item.color, marginRight: 4 }}>{item.icon}</span>}
                />
              </Card>
            </Col>
          ))}
        </Row>

        {stats && (
          <div style={{ marginTop: 12 }}>
            <Alert
              type="info"
              showIcon
              message="脏页（Dirty Pages）"
              description={
                <span style={{ fontFamily: MONO, fontSize: 12 }}>
                  {stats.dirty_pages?.length
                    ? stats.dirty_pages.join(', ')
                    : '当前无脏页，Checkpoint 已将所有修改刷盘（FR-2.4）'}
                </span>
              }
            />
          </div>
        )}
      </div>
    </div>
  )
}
