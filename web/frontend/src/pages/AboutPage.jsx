import {
  Alert,
  Button,
  Card,
  Descriptions,
  Space,
  Steps,
  Tag,
  Typography,
} from 'antd'
import { ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons'
import ideColors from '../theme'
import PageHeader from '../components/PageHeader'

const MONO = "Consolas, 'Cascadia Code', 'JetBrains Mono', 'Courier New', monospace"

const PIPELINE = [
  { title: 'SQL 输入', description: '控制台 / REST API' },
  { title: 'SQL 编译器', description: '词法 → 语法 → 语义' },
  { title: '逻辑执行计划', description: '含常量折叠优化' },
  { title: '数据库引擎', description: '算子执行 + 表达式求值' },
  { title: '页式存储', description: '4KB 页 / 缓存 / Checkpoint' },
]

const FEATURES = [
  { name: 'CREATE TABLE', desc: '建表并登记系统目录' },
  { name: 'INSERT（多行）', desc: 'VALUES 多行一次性插入' },
  { name: 'SELECT ... WHERE', desc: '顺序扫描 + 条件过滤 + 投影' },
  { name: 'DELETE ... WHERE', desc: '删除标记与整页回收' },
  { name: '页缓存 LRU / FIFO', desc: '命中统计与替换日志' },
  { name: '持久化', desc: '重启后表结构与数据保留' },
]

const LIMITS = [
  '无一元负号：-1 不能作为字面量',
  '不支持科学计数法（1e3 报 LexError）',
  '空语句非法：孤立分号 ; 与连续分号 ;; 均报 ParseError',
  '仅末尾缺分号宽容：中间缺分号仍报错',
]

export default function AboutPage({ health, onHealthChange }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <PageHeader
        title="关于 EchoSQL"
        subtitle="中南大学《大型平台软件设计实习》课程设计 · MiniDB 数据库管理系统"
        extra={
          <Button size="small" icon={<ReloadOutlined />} onClick={onHealthChange}>
            刷新环境
          </Button>
        }
      />
      <div style={{ padding: 12, overflow: 'auto', flex: 1 }}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Card
            size="small"
            title={
              <Space>
                <ThunderboltOutlined style={{ color: ideColors.blue }} />
                <span>系统链路</span>
              </Space>
            }
          >
            <Steps
              size="small"
              current={-1}
              items={PIPELINE.map((p) => ({ title: p.title, description: p.description }))}
              style={{ paddingBottom: 4 }}
            />
          </Card>

          <Card size="small" title="运行环境（GET /api/health）">
            <Descriptions
              size="small"
              column={{ xs: 1, sm: 2 }}
              bordered
              items={[
                { key: 'service', label: '服务', children: health?.service ?? '–' },
                {
                  key: 'status',
                  label: '状态',
                  children: health?.status === 'ok'
                    ? <Tag color="success">ok</Tag>
                    : <Tag color="error">不可用</Tag>,
                },
                {
                  key: 'python',
                  label: 'Python',
                  children: <span style={{ fontFamily: MONO }}>{health?.python ?? '–'}</span>,
                },
                {
                  key: 'flask',
                  label: 'Flask',
                  children: <span style={{ fontFamily: MONO }}>{health?.flask ?? '–'}</span>,
                },
                {
                  key: 'pytest',
                  label: 'pytest',
                  children: <span style={{ fontFamily: MONO }}>{health?.pytest ?? '–'}</span>,
                },
                {
                  key: 'platform',
                  label: '平台',
                  children: <span style={{ fontFamily: MONO, fontSize: 12 }}>{health?.platform ?? '–'}</span>,
                },
                {
                  key: 'frontend',
                  label: '前端',
                  children: <span style={{ fontFamily: MONO }}>React 18 + Ant Design 5 (Vite)</span>,
                },
                {
                  key: 'theme',
                  label: '配色',
                  children: <span style={{ fontFamily: MONO }}>VS Code Dark+（#1e1e1e / #007acc）</span>,
                },
              ]}
            />
          </Card>

          <Card size="small" title="已实现能力">
            <Space wrap size={8}>
              {FEATURES.map((f) => (
                <Tag key={f.name} style={{ fontFamily: MONO, padding: '4px 8px' }}>
                  <span style={{ color: '#ffffff' }}>{f.name}</span>
                  <span style={{ color: ideColors.textDim }}> · {f.desc}</span>
                </Tag>
              ))}
            </Space>
          </Card>

          <Alert
            type="warning"
            showIcon
            message="已知限制（文法内不承诺，不视为缺陷）"
            description={
              <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                {LIMITS.map((l) => (
                  <li key={l} style={{ fontSize: 12 }}>
                    <Typography.Text style={{ fontSize: 12 }}>{l}</Typography.Text>
                  </li>
                ))}
              </ul>
            }
          />

          <div style={{ color: ideColors.textDim, fontSize: 12, textAlign: 'center', padding: '8px 0 16px' }}>
            EchoSQL · MiniDB —— SQL → 执行计划 → 数据页 完整链路
          </div>
        </Space>
      </div>
    </div>
  )
}
