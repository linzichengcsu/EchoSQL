import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  App as AntApp,
  Button,
  Empty,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { ReloadOutlined, DatabaseOutlined } from '@ant-design/icons'
import { fetchTables } from '../api'
import ideColors from '../theme'
import PageHeader from '../components/PageHeader'

const MONO = "Consolas, 'Cascadia Code', 'JetBrains Mono', 'Courier New', monospace"

export default function TablesPage() {
  const { message } = AntApp.useApp()
  const [tables, setTables] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await fetchTables()
      setTables(data.tables || [])
    } catch {
      setError('加载表结构失败，请确认后端服务已启动')
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const columns = [
    {
      title: '表名',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      render: (name) => (
        <Space>
          <DatabaseOutlined style={{ color: ideColors.blue }} />
          <Typography.Text strong style={{ fontFamily: MONO, color: ideColors.yellow }}>
            {name}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '列定义',
      dataIndex: 'columns',
      key: 'columns',
      render: (cols) =>
        (cols || []).map((c) => (
          <Tag key={`${c.name}`} style={{ fontFamily: MONO, marginBottom: 4 }}>
            <span style={{ color: '#ffffff' }}>{c.name}</span>
            <span style={{ color: ideColors.blue }}> : {c.type}</span>
          </Tag>
        )),
    },
    {
      title: '数据页',
      dataIndex: 'pages',
      key: 'pages',
      width: 140,
      render: (pages) => (
        <Tooltip title={pages?.length ? `页 ID：${pages.join(', ')}` : '无数据页'}>
          <Tag style={{ fontFamily: MONO }}>{pages?.length ?? 0} 页</Tag>
        </Tooltip>
      ),
    },
  ]

  const dataSource = tables.map((t) => ({ ...t, key: t.name }))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <PageHeader
        title="数据表"
        subtitle="系统目录（Catalog）：表结构以元数据特殊表持久化（FR-3.3）"
        extra={
          <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={load}>
            刷新
          </Button>
        }
      />
      <div style={{ padding: 12, overflow: 'auto', flex: 1 }}>
        {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}
        {!loading && !error && tables.length === 0 ? (
          <Empty
            description="当前数据库没有任何表，请先在 SQL 控制台执行 CREATE TABLE"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            style={{ marginTop: 48 }}
          />
        ) : (
          <Table
            size="small"
            bordered
            rowKey="name"
            loading={loading}
            columns={columns}
            dataSource={dataSource}
            pagination={false}
            locale={{ emptyText: '暂无表' }}
          />
        )}
      </div>
    </div>
  )
}
