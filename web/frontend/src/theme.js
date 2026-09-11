// 经典 IDE 配色（VS Code Dark+）与 Ant Design 主题配置
export const ideColors = {
  bg: '#1e1e1e',            // 编辑器 / 页面底色
  bgContainer: '#252526',   // 容器、面板
  bgElevated: '#2d2d30',    // 悬浮 / 弹层
  bgHover: '#2a2d2e',
  border: '#3c3c3c',
  borderLight: '#2d2d2d',
  text: '#d4d4d4',
  textDim: '#9d9d9d',
  textDisabled: '#6f6f6f',
  accent: '#007acc',        // VS Code 蓝
  accentHover: '#1177bb',
  statusBar: '#007acc',
  green: '#89d185',
  red: '#f48771',
  yellow: '#dcdcaa',
  blue: '#569cd6',
  purple: '#c586c0',
  orange: '#ce9178',
  gutter: '#858585',
}

export const antdTheme = {
  cssVar: true,
  token: {
    colorPrimary: ideColors.accent,
    colorInfo: ideColors.accent,
    colorSuccess: ideColors.green,
    colorError: ideColors.red,
    colorWarning: '#d7ba7d',
    colorBgBase: ideColors.bg,
    colorBgContainer: ideColors.bgContainer,
    colorBgElevated: ideColors.bgElevated,
    colorBgLayout: ideColors.bg,
    colorBorder: ideColors.border,
    colorBorderSecondary: ideColors.borderLight,
    colorText: ideColors.text,
    colorTextSecondary: '#b8b8b8',
    colorTextTertiary: ideColors.textDim,
    colorTextQuaternary: ideColors.textDisabled,
    borderRadius: 4,
    fontFamily: "'Segoe UI', 'Microsoft YaHei', system-ui, -apple-system, sans-serif",
    fontFamilyCode: "Consolas, 'Cascadia Code', 'JetBrains Mono', 'Courier New', monospace",
  },
  components: {
    Layout: {
      bodyBg: ideColors.bg,
      headerBg: ideColors.bgContainer,
      siderBg: ideColors.bgContainer,
      headerHeight: 40,
      headerPadding: '0 16px',
    },
    Menu: {
      darkItemBg: ideColors.bgContainer,
      darkItemSelectedBg: '#37373d',
      darkItemSelectedColor: '#ffffff',
      darkItemHoverBg: ideColors.bgHover,
      itemBorderRadius: 0,
      itemMarginInline: 0,
      itemHeight: 36,
    },
    Table: {
      headerBg: ideColors.bgElevated,
      headerColor: ideColors.text,
      rowHoverBg: 'rgba(0,122,204,0.12)',
      cellPaddingBlock: 8,
      cellPaddingInline: 10,
    },
    Tabs: {
      itemSelectedColor: '#ffffff',
      itemHoverColor: ideColors.text,
    },
    Input: {
      colorBgContainer: ideColors.bg,
      activeBorderColor: ideColors.accent,
      hoverBorderColor: '#4a4a4a',
    },
    TextArea: {
      colorBgContainer: ideColors.bg,
      activeBorderColor: ideColors.accent,
    },
    Card: {
      colorBgContainer: ideColors.bgContainer,
    },
    Alert: {
      colorErrorBg: 'rgba(244,135,113,0.10)',
      colorSuccessBg: 'rgba(137,209,133,0.10)',
      colorInfoBg: 'rgba(86,156,214,0.10)',
    },
    Progress: {
      defaultColor: ideColors.accent,
    },
    Tag: {
      defaultBg: 'rgba(0,122,204,0.16)',
      defaultColor: ideColors.blue,
    },
    Statistic: {
      contentFontSize: 26,
    },
  },
}

export default ideColors
