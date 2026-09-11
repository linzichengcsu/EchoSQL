import { useEffect, useState } from 'react'
import { Layout, Menu, Badge, Tooltip, Typography } from 'antd'
import {
  CodeOutlined,
  DatabaseOutlined,
  BarChartOutlined,
  InfoCircleOutlined,
  ThunderboltOutlined,
  ApiOutlined,
} from '@ant-design/icons'
import ideColors from './theme'
import { fetchHealth } from './api'
import ConsolePage from './pages/ConsolePage'
import TablesPage from './pages/TablesPage'
import StatsPage from './pages/StatsPage'
import AboutPage from './pages/AboutPage'

const { Header, Sider, Content, Footer } = Layout

const MENU = [
  { key: 'console', icon: <CodeOutlined />, label: 'SQL 控制台' },
  { key: 'tables', icon: <DatabaseOutlined />, label: '数据表' },
  { key: 'stats', icon: <BarChartOutlined />, label: '运行统计' },
  { key: 'about', icon: <InfoCircleOutlined />, label: '关于' },
]

const PAGES = {
  console: ConsolePage,
  tables: TablesPage,
  stats: StatsPage,
  about: AboutPage,
}

export default function App() {
  const [active, setActive] = useState('console')
  const [health, setHealth] = useState(null)
  const [online, setOnline] = useState(false)
  const [checking, setChecking] = useState(false)

  const refreshHealth = async () => {
    setChecking(true)
    try {
      const { data } = await fetchHealth()
      setHealth(data)
      setOnline(Boolean(data && data.status === 'ok'))
    } catch {
      setHealth(null)
      setOnline(false)
    } finally {
      setChecking(false)
    }
  }

  useEffect(() => {
    refreshHealth()
    const timer = setInterval(refreshHealth, 15000)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const Page = PAGES[active] || ConsolePage

  return (
    <Layout style={{ height: '100vh' }}>
      {/* 顶部标题栏（仿 IDE 标题栏） */}
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          borderBottom: `1px solid ${ideColors.border}`,
        }}
      >
        <ThunderboltOutlined style={{ color: ideColors.blue, fontSize: 18 }} />
        <Typography.Text strong style={{ color: '#ffffff', fontSize: 14 }}>
          EchoSQL <span style={{ color: ideColors.textDim, fontWeight: 400 }}>MiniDB</span>
        </Typography.Text>
        <span style={{ flex: 1 }} />
        <Tooltip title={online ? '后端服务在线' : '后端服务离线'}>
          <Badge
            status={online ? 'success' : 'error'}
            text={<span style={{ color: ideColors.textDim, fontSize: 12 }}>{online ? '已连接' : '未连接'}</span>}
          />
        </Tooltip>
      </Header>

      <Layout>
        {/* 左侧导航（仿 IDE 侧边栏） */}
        <Sider
          width={180}
          theme="dark"
          style={{ borderRight: `1px solid ${ideColors.border}` }}
        >
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[active]}
            items={MENU}
            onClick={({ key }) => setActive(key)}
            style={{ height: '100%', borderInlineEnd: 'none' }}
          />
        </Sider>

        {/* 主内容区 */}
        <Content style={{ overflow: 'auto' }}>
          <Page health={health} onHealthChange={refreshHealth} />
        </Content>
      </Layout>

      {/* 底部状态栏（仿 IDE 状态栏） */}
      <Footer
        style={{
          height: 24,
          padding: '0 12px',
          lineHeight: '24px',
          background: ideColors.statusBar,
          color: '#ffffff',
          fontSize: 12,
          display: 'flex',
          alignItems: 'center',
          gap: 16,
        }}
      >
        <span><ApiOutlined /> {online ? 'http://127.0.0.1:5000' : '后端离线'}</span>
        <span style={{ opacity: 0.85 }}>{checking ? '检查中…' : ''}</span>
        <span style={{ flex: 1 }} />
        <span style={{ opacity: 0.85 }}>SQL → 执行计划 → 数据页</span>
        <span style={{ opacity: 0.85 }}>MiniDB v1.0</span>
      </Footer>
    </Layout>
  )
}
