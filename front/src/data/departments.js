export const departments = [
  {
    code: 'BUE1',
    name: 'BUE1',
    tone: '商机推进',
    summary: '面向核心客户推进线索分发、跟进节奏和销售资料的统一协作。',
    tools: [
      { id: 'pipeline_tracker', name: '功能开发中', tag: 'Pipeline', description: '商机推进台功能开发中。' },
      { id: 'lead_center', name: '功能开发中', tag: 'Leads', description: '线索整编功能开发中。' },
      { id: 'meeting_notes', name: '功能开发中', tag: 'Notes', description: '拜访纪要功能开发中。' },
    ],
  },
  {
    code: 'BUE2',
    name: 'BUE2',
    tone: '报价协同',
    summary: '聚焦报价协同、排期沟通和交付节奏，让跨团队协作更顺畅。',
    tools: [
      {
        id: 'test',
        name: '测试功能',
        tag: 'Test',
        description: '等待 5 秒后返回结果，用于验证异步执行和实时日志展示是否正常。',
        action: 'run_script',
      },
      {
        id: 'citeo_email_extractor',
        name: 'FR-Citeo 注销成功名单邮件提取',
        tag: 'Email',
        description: "连接 163 邮箱，提取主题包含“Citeo - Réf. client n°”的邮件并解析注销成功名单。",
        action: 'run_script',
        configurable: true,
      },
    ],
  },
  {
    code: 'BUE3',
    name: 'BUE3',
    tone: '资产中心',
    summary: '支持日常经营数据、可视化看板和资料资产的集中管理。',
    tools: [
      { id: 'daily_sync', name: '功能开发中', tag: 'Daily', description: '日报同步功能开发中。' },
      { id: 'board_view', name: '功能开发中', tag: 'Board', description: '经营看板功能开发中。' },
      { id: 'asset_library', name: '功能开发中', tag: 'Assets', description: '资产中心功能开发中。' },
    ],
  },
  {
    code: 'BUV1',
    name: 'BUV1',
    tone: '内容发布',
    summary: '覆盖内容策划、媒体排期和发布执行的完整协同流程。',
    tools: [
      { id: 'campaign_plan', name: '功能开发中', tag: 'Plan', description: '排期规划功能开发中。' },
      { id: 'media_pack', name: '功能开发中', tag: 'Media', description: '媒体素材功能开发中。' },
      { id: 'publish_hub', name: '功能开发中', tag: 'Publish', description: '发布中心功能开发中。' },
    ],
  },
  {
    code: 'BUV2',
    name: 'BUV2',
    tone: '投放运营',
    summary: '聚焦投放排班、广告素材和效果汇总，提升运营协同效率。',
    tools: [
      { id: 'roster_board', name: '功能开发中', tag: 'Roster', description: '排班台功能开发中。' },
      { id: 'ad_studio', name: '功能开发中', tag: 'Ads', description: '广告工坊功能开发中。' },
      { id: 'report_center', name: '功能开发中', tag: 'Report', description: '效果报告功能开发中。' },
    ],
  },
  {
    code: 'BUV3',
    name: 'BUV3',
    tone: '品牌系统',
    summary: '围绕品牌活动、创意提案和执行规范打造统一协同空间。',
    tools: [
      { id: 'campaign_board', name: '功能开发中', tag: 'Brand', description: '品牌项目协同功能开发中。' },
      { id: 'idea_pool', name: '功能开发中', tag: 'Idea', description: '创意池功能开发中。' },
      { id: 'brand_guide', name: '功能开发中', tag: 'Guide', description: '品牌规范功能开发中。' },
    ],
  },
  {
    code: 'CONSULT',
    name: '顾问部',
    tone: '单据自动化',
    summary: '把跨境单据处理流程从手工核对升级为可配置、可预览、可执行的自动化作业。',
    tools: [
      {
        id: 'test_hello',
        name: '测试功能',
        tag: 'Test',
        description: '系统测试工具，用于验证自动化服务是否正常运行。',
        action: 'run_script',
      },
      {
        id: 'invoice_recognizer',
        name: '英德单据识别',
        tag: 'RPA',
        description: '识别英国与德国递延税单据，提取关键税务字段并输出结果。',
        action: 'run_script',
        previewable: true,
        configurable: true,
      },
    ],
  },
  {
    code: 'OPS',
    name: '运营部',
    tone: '运营节奏',
    summary: '连接指标看板、工作日历和渠道协同，形成清晰的运营节奏。',
    tools: [
      { id: 'calendar_sync', name: '功能开发中', tag: 'Calendar', description: '运营日历功能开发中。' },
      { id: 'channel_map', name: '功能开发中', tag: 'Channel', description: '渠道地图功能开发中。' },
    ],
  },
]
