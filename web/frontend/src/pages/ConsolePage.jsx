import { useState } from 'react'
import {
  Alert,
  App as AntApp,
  Button,
  Empty,
  Input,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  PlayCircleOutlined,
  ClearOutlined,
  HistoryOutlined,
  TableOutlined,
  MessageOutlined,
} from '@ant-design/icons'
import { runSql } from '../api'
import ideColors from '../theme'
import PageHeader from '../components/PageHeader'

const MONO = "Consolas, 'Cascadia Code', 'JetBrains Mono', 'Courier New', monospace"

const DEFAULT_SQL = `-- 支持：CREATE TABLE / INSERT / SELECT(WHERE) / DELETE
-- Ctrl + Enter 执行
SELECT id, name FROM student WHERE age > 18;`

const SAMPLES = [
  { value: 'create', label: '建表 student', sql: 'CREATE TABLE student(id INT, name VARCHAR, age INT);' },
  {
    value: 'insert',
    label: '插入多行数据',
    sql: "INSERT INTO student(id, name, age) VALUES (1,'Alice',20),(2,'Bob',17),(3,'Carol',22),(4,'Dan',19),(5,'Eve',21);",
  },
  { value: 'select', label: '条件查询', sql: 'SELECT id, name FROM student WHERE age > 18;' },
  { value: 'select_all', label: '查询全部', sql: 'SELECT * FROM student;' },
  { value: 'delete', label: '条件删除', sql: 'DELETE FROM student WHERE id = 2;' },
]

/** NULL 值统一以斜体灰字呈现 */
function Cell({ value }) {
  if (value === null || value === undefined) {
    return <span style={{ color: ideColors.textDisabled, fontStyle: 'italic' }}>NULL</span>
  }
  return <span>{String(value)}</span>
}

/** SELECT 结果表格 */
function SelectResult({ columns = [], rows = [] }) {
  const tableColumns = [
    {
      title: '',
      dataIndex: '__idx',
      key: '__idx',
      width: 48,
      align: 'right',
      render: (v) => <span style={{ color: ideColors.gutter, fontFamily: MONO }}>{v}</span>,
    },
    ...columns.map((col, i) => ({
      title: col,
      dataIndex: `c${i}`,
      key: `c${i}`,
      ellipsis: true,
      render: (v) => <Cell value={v} />,
    })),
  ]

  const dataSource = rows.map((row, ri) => {
    const record = { key: ri, __idx: ri + 1 }
    row.forEach((value, ci) => {
      record[`c${ci}`] = value
    })
    return record
  })

  if (!columns.length) {
    return <Empty description="(empty result)" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  }

  return (
    <Table
      size="small"
      bordered
      columns={tableColumns}
      dataSource={dataSource}
      pagination={rows.length > 20 ? { pageSize: 20, size: 'small', showSizeChanger: false } : false}
      scroll={{ x: 'max-content' }}
      locale={{ emptyText: <Empty description="0 行" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
    />
  )
}

/** 非查询语句 / 错误的结果提示 */
function MessageResult({ result }) {
  if (!result) return <Empty description="尚未执行任何语句" image={Empty.PRESENTED_IMAGE_SIMPLE} />

  if (result.ok === false) {
    return (
      <Alert
        type="error"
        showIcon
        message={
          <Space size={8}>
            <Tag color="error" style={{ fontFamily: MONO }}>{result.kind || 'ERROR'}</Tag>
            {result.position ? (
              <span style={{ color: ideColors.textDim, fontSize: 12 }}>
                位置 {result.position[0]}:{result.position[1]}
              </span>
            ) : null}
          </Space>
        }
        description={<span style={{ fontFamily: MONO, fontSize: 13 }}>{result.error}</span>}
      />
    )
  }

  const text =
    result.kind === 'EMPTY' ? '空输入（不含任何语句）' : result.message || `${result.kind} 执行成功`

  return (
    <Alert
      type={result.kind === 'EMPTY' ? 'info' : 'success'}
      showIcon
      message={
        <Space size={8}>
          <Tag color={result.kind === 'EMPTY' ? 'default' : 'success'} style={{ fontFamily: MONO }}>
            {result.kind}
          </Tag>
          <span style={{ fontFamily: MONO, fontSize: 13 }}>{text}</span>
        </Space>
      }
      description={
        result.rows_affected
          ? <span style={{ color: ideColors.textDim, fontSize: 12 }}>影响行数：{result.rows_affected}</span>
          : null
      }
    />
  )
}

export default function ConsolePage() {
  const { message } = AntApp.useApp()
  const [sql, setSql] = useState(DEFAULT_SQL)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [history, setHistory] = useState([])
  const [tab, setTab] = useState('result')

  const execute = async () => {
    if (!sql.trim()) {
      message.warning('请输入 SQL 语句')
      return
    }
    setLoading(true)
    const started = performance.now()
    try {
      const { data } = await runSql(sql)
      const duration = Math.round(performance.now() - started)
      const entry = {
        id: `${Date.now()}-${Math.random().toString(16).slice(2, 6)}`,
        sql,
        ok: data.ok !== false,
        kind: data.kind,
        summary: data.ok === false
          ? data.error
          : data.kind === 'SELECT'
            ? `${data.rows?.length ?? 0} 行`
            : data.message || data.kind,
        duration,
        at: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      }
      setResult({ ...data, duration, sql })
      setHistory((list) => [entry, ...list].slice(0, 50))
      setTab('result')
      if (data.ok === false) {
        message.error(data.error || '执行失败')
      } else if (data.kind === 'SELECT') {
        message.success(`查询完成：${data.rows?.length ?? 0} 行，耗时 ${duration} ms`)
      } else {
        message.success(`${data.message || data.kind}（${duration} ms）`)
      }
    } catch (err) {
      setResult({ ok: false, kind: 'NETWORK', error: `请求失败：${err}` })
      message.error('请求失败，请确认 Flask 后端已启动')
    } finally {
      setLoading(false)
    }
  }

  const onKeyDown = (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault()
      execute()
    }
  }

  const historyColumns = [
    { title: '时间', dataIndex: 'at', key: 'at', width: 92 },
    {
      title: '状态',
      dataIndex: 'kind',
      key: 'kind',
      width: 110,
      render: (_, row) => (
        <Tag color={row.ok ? 'success' : 'error'} style={{ fontFamily: MONO }}>
          {row.ok ? row.kind : 'ERROR'}
        </Tag>
      ),
    },
    {
      title: '语句',
      dataIndex: 'sql',
      key: 'sql',
      ellipsis: true,
      render: (text) => (
        <Tooltip title={<pre style={{ margin: 0, fontFamily: MONO, fontSize: 12 }}>{text}</pre>}>
          <span style={{ fontFamily: MONO, fontSize: 12 }}>{text.replace(/\s+/g, ' ').trim()}</span>
        </Tooltip>
      ),
    },
    {
      title: '结果 / 错误',
      dataIndex: 'summary',
      key: 'summary',
      ellipsis: true,
      render: (text) => <span style={{ fontSize: 12, color: ideColors.textDim }}>{text}</span>,
    },
    { title: '耗时', dataIndex: 'duration', key: 'duration', width: 80, render: (v) => `${v} ms` },
    {
      title: '',
      key: 'action',
      width: 68,
      render: (_, row) => (
        <Button size="small" type="link" onClick={() => setSql(row.sql)}>
          回填
        </Button>
      ),
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <PageHeader
        title="SQL 控制台"
        subtitle="输入 SQL → 词法/语法/语义分析 → 逻辑计划 → 引擎执行 → 结果"
        extra={
          <>
            <Select
              placeholder="插入示例 SQL"
              style={{ width: 150 }}
              size="small"
              value={null}
              options={SAMPLES.map((s) => ({ value: s.value, label: s.label }))}
              onChange={(value) => {
                const sample = SAMPLES.find((s) => s.value === value)
                if (sample) {
                  setSql(sample.sql)
                  message.info(`已载入示例：${sample.label}`)
                }
              }}
            />
            <Button size="small" icon={<ClearOutlined />} onClick={() => setSql('')}>
              清空
            </Button>
            <Button
              size="small"
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={loading}
              onClick={execute}
            >
              执行 (Ctrl+Enter)
            </Button>
          </>
        }
      />

      <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12, flex: 1, minHeight: 0 }}>
        {/* 编辑器（仿 IDE 编辑区） */}
        <div
          style={{
            border: `1px solid ${ideColors.border}`,
            borderRadius: 4,
            background: ideColors.bg,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 10px',
              background: ideColors.bgContainer,
              borderBottom: `1px solid ${ideColors.border}`,
              fontSize: 12,
              color: ideColors.textDim,
            }}
          >
            <TableOutlined />
            <span>query.sql</span>
            <span style={{ flex: 1 }} />
            {result?.duration ? (
              <span>上次耗时 {result.duration} ms</span>
            ) : (
              <span>Ctrl + Enter 执行</span>
            )}
          </div>
          <Input.TextArea
            value={sql}
            onChange={(e) => setSql(e.target.value)}
            onKeyDown={onKeyDown}
            autoSize={{ minRows: 7, maxRows: 16 }}
            spellCheck={false}
            style={{
              fontFamily: MONO,
              fontSize: 13,
              lineHeight: '20px',
              background: ideColors.bg,
              color: ideColors.text,
              border: 'none',
              boxShadow: 'none',
              borderRadius: 0,
              padding: '10px 12px',
              resize: 'none',
            }}
          />
        </div>

        {/* 结果区 */}
        <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
          <Tabs
            size="small"
            activeKey={tab}
            onChange={setTab}
            items={[
              {
                key: 'result',
                label: (
                  <span>
                    <TableOutlined /> 结果
                    {result?.kind === 'SELECT' && result.ok !== false ? (
                      <Tag style={{ marginLeft: 8 }}>{result.rows?.length ?? 0} 行</Tag>
                    ) : null}
                  </span>
                ),
                children: (
                  <div>
                    {result?.ok !== false && result?.kind === 'SELECT' ? (
                      <SelectResult columns={result.columns} rows={result.rows} />
                    ) : (
                      <MessageResult result={result} />
                    )}
                  </div>
                ),
              },
              {
                key: 'message',
                label: (
                  <span>
                    <MessageOutlined /> 消息
                  </span>
                ),
                children: (
                  <div>
                    {result && result.ok !== false && result.kind === 'SELECT' ? (
                      <Alert
                        type="success"
                        showIcon
                        message={`查询完成：返回 ${result.rows?.length ?? 0} 行`}
                        description={
                          <span style={{ fontFamily: MONO, fontSize: 12 }}>
                            列：{result.columns?.join(', ')} · 耗时 {result.duration} ms
                          </span>
                        }
                      />
                    ) : (
                      <MessageResult result={result} />
                    )}
                  </div>
                ),
              },
              {
                key: 'history',
                label: (
                  <span>
                    <HistoryOutlined /> 历史
                    {history.length ? <Tag style={{ marginLeft: 8 }}>{history.length}</Tag> : null}
                  </span>
                ),
                children: history.length ? (
                  <Table
                    size="small"
                    rowKey="id"
                    columns={historyColumns}
                    dataSource={history}
                    pagination={{ pageSize: 10, size: 'small', showSizeChanger: false }}
                  />
                ) : (
                  <Empty description="暂无执行历史" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ),
              },
            ]}
          />
        </div>
      </div>
    </div>
  )
}
