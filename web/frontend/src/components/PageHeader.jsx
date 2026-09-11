import { Space, Typography } from 'antd'
import ideColors from '../theme'

/** 统一的页面标题栏：左侧标题 + 右侧操作区 */
export default function PageHeader({ title, subtitle, extra }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '12px 16px',
        borderBottom: `1px solid ${ideColors.border}`,
        background: ideColors.bgContainer,
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <Typography.Text strong style={{ fontSize: 14, color: '#ffffff' }}>
          {title}
        </Typography.Text>
        {subtitle ? (
          <div style={{ color: ideColors.textDim, fontSize: 12, marginTop: 2 }}>{subtitle}</div>
        ) : null}
      </div>
      {extra ? <Space>{extra}</Space> : null}
    </div>
  )
}
