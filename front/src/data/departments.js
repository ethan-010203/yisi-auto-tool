export const departmentNetworkPaths = {
  BUE1: '\\\\192.168.76.93\\厦门部门\\BUE1',
  BUE2: '\\\\192.168.76.93\\厦门部门\\BUE2',
  BUV1: '\\\\192.168.76.93\\厦门部门\\BUV1',
  BUV2: '\\\\192.168.76.93\\厦门部门\\BUV2',
  BUV3: '\\\\192.168.76.93\\厦门部门\\BUV3',
  CONSULT: '\\\\192.168.76.93\\厦门部门\\顾问部',
}

export const departments = [
  {
    code: 'BUE1',
    name: 'BUE1',
    tone: 'regulatory',
    summary: 'BUE1 申报与法规自动化工具集合。',
    tools: [
      {
        id: 'ear_declaration_data_fetcher',
        name: 'EAR官网申报数据抓取',
        tag: 'EAR',
        description: '读取申报数据 Excel 文件夹，结合 EAR 网页账号密码，为后续抓取官网申报结果提供运行骨架。',
        action: 'run_script',
        configurable: true,
      },
    ],
  },
  {
    code: 'BUE2',
    name: 'BUE2',
    tone: 'operations',
    summary: 'BUE2 自动化执行工具集合。',
    tools: [
      {
        id: 'test',
        name: '测试脚本',
        tag: 'Test',
        description: '用于验证脚本运行链路与日志输出。',
        action: 'run_script',
      },
      {
        id: 'queue_runtime_probe',
        name: '队列运行探针',
        tag: 'Queue',
        description: '用于验证任务排队、运行时目录和实时日志能力。',
        action: 'run_script',
      },
      {
        id: 'citeo_email_extractor',
        name: 'FR-Citeo 邮件编号提取',
        tag: 'Email',
        description: '从 163 邮箱指定文件夹提取 Citeo 邮件里的客户编号并导出结果。',
        action: 'run_script',
        configurable: true,
      },
    ],
  },
  {
    code: 'BUV1',
    name: 'BUV1',
    tone: 'growth',
    summary: 'BUV1 工具位预留。',
    tools: [
      { id: 'campaign_plan', name: '活动规划', tag: 'Plan', description: '预留工具位。' },
      { id: 'media_pack', name: '素材包管理', tag: 'Media', description: '预留工具位。' },
      { id: 'publish_hub', name: '发布中心', tag: 'Publish', description: '预留工具位。' },
    ],
  },
  {
    code: 'BUV2',
    name: 'BUV2',
    tone: 'delivery',
    summary: 'BUV2 工具位预留。',
    tools: [
      { id: 'roster_board', name: '排期面板', tag: 'Roster', description: '预留工具位。' },
      { id: 'ad_studio', name: '广告工作台', tag: 'Ads', description: '预留工具位。' },
      { id: 'report_center', name: '报告中心', tag: 'Report', description: '预留工具位。' },
    ],
  },
  {
    code: 'BUV3',
    name: 'BUV3',
    tone: 'brand',
    summary: 'BUV3 工具位预留。',
    tools: [
      { id: 'campaign_board', name: '品牌项目板', tag: 'Brand', description: '预留工具位。' },
      { id: 'idea_pool', name: '灵感池', tag: 'Idea', description: '预留工具位。' },
      { id: 'brand_guide', name: '品牌指南', tag: 'Guide', description: '预留工具位。' },
    ],
  },
  {
    code: 'CONSULT',
    name: '顾问部',
    tone: 'consulting',
    summary: '顾问部自动化工具集合。',
    tools: [
      {
        id: 'test_hello',
        name: '测试脚本',
        tag: 'Test',
        description: '用于验证顾问部脚本运行链路。',
        action: 'run_script',
      },
      {
        id: 'queue_runtime_probe',
        name: '队列运行探针',
        tag: 'Queue',
        description: '用于验证任务排队、运行时目录和实时日志能力。',
        action: 'run_script',
      },
      {
        id: 'invoice_recognizer',
        name: '英德单据识别',
        tag: 'RPA',
        description: '识别共享目录中的单据并处理 Excel 清单。',
        action: 'run_script',
        configurable: true,
      },
    ],
  },
]
