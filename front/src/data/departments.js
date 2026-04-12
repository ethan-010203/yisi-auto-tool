export const departments = [
  {
    code: 'BUE1',
    name: 'BUE1',
    tone: 'Pipeline Ops',
    summary: '面向核心客户推进线索分发、跟进节奏和销售资料的统一协作。',
    tools: [
      { id: 'pipeline_tracker', name: '商机推进台', tag: 'Pipeline', description: '统一查看商机推进状态和下一步动作。' },
      { id: 'lead_center', name: '线索整编', tag: 'Leads', description: '把零散线索收拢成可分配、可追踪的名单。' },
      { id: 'meeting_notes', name: '拜访纪要', tag: 'Notes', description: '快速沉淀客户沟通记录与关键信息。' },
    ],
  },
  {
    code: 'BUE2',
    name: 'BUE2',
    tone: 'Quote Flow',
    summary: '聚焦报价协同、排期沟通和交付节奏，让跨团队协作更顺畅。',
    tools: [
      { id: 'schedule_board', name: '排期看板', tag: 'Schedule', description: '掌握项目节点、资源占用和交付风险。' },
      { id: 'quote_builder', name: '报价助手', tag: 'Quote', description: '减少重复制作报价单的时间成本。' },
      { id: 'review_queue', name: '审核视图', tag: 'Review', description: '把待审核事项按优先级清晰排队。' },
    ],
  },
  {
    code: 'BUE3',
    name: 'BUE3',
    tone: 'Asset Center',
    summary: '支撑日常经营数据、可视化看板和资料资产的集中管理。',
    tools: [
      { id: 'daily_sync', name: '日报同步', tag: 'Daily', description: '同步团队日报与关键经营信号。' },
      { id: 'board_view', name: '经营看板', tag: 'Board', description: '汇总关键指标并快速定位异常。' },
      { id: 'asset_library', name: '资产中心', tag: 'Assets', description: '沉淀可复用模板、案例和素材。' },
    ],
  },
  {
    code: 'BUV1',
    name: 'BUV1',
    tone: 'Publishing',
    summary: '覆盖内容策划、媒体排期和发布执行的完整协同流程。',
    tools: [
      { id: 'campaign_plan', name: '排期规划', tag: 'Plan', description: '整合选题、发布时间和负责人安排。' },
      { id: 'media_pack', name: '媒体素材', tag: 'Media', description: '统一管理发布所需图片、视频与文案。' },
      { id: 'publish_hub', name: '发布中心', tag: 'Publish', description: '集中执行内容投放与复盘。' },
    ],
  },
  {
    code: 'BUV2',
    name: 'BUV2',
    tone: 'Ad Ops',
    summary: '聚焦投放排班、广告素材和效果汇总，提升运营协同效率。',
    tools: [
      { id: 'roster_board', name: '排班台', tag: 'Roster', description: '安排值班节奏与人力分布。' },
      { id: 'ad_studio', name: '广告工坊', tag: 'Ads', description: '统一管理投放所需创意物料。' },
      { id: 'report_center', name: '效果报告', tag: 'Report', description: '汇总关键投放表现并快速导出。' },
    ],
  },
  {
    code: 'BUV3',
    name: 'BUV3',
    tone: 'Brand System',
    summary: '围绕品牌活动、创意提案和执行规范打造统一协同空间。',
    tools: [
      { id: 'campaign_board', name: 'Campaign Board', tag: 'Brand', description: '同步品牌项目里程碑和关键事项。' },
      { id: 'idea_pool', name: '创意池', tag: 'Idea', description: '沉淀创意方向与提案线索。' },
      { id: 'brand_guide', name: '执行指南', tag: 'Guide', description: '统一品牌资产、口径与规范。' },
    ],
  },
  {
    code: 'CONSULT',
    name: '顾问部',
    tone: 'Document Automation',
    summary: '把跨境单据处理流程从手工核对升级为可配置、可预览、可执行的自动化作业。',
    tools: [
      {
        id: 'test_hello',
        name: '测试功能',
        tag: 'Test',
        description: '系统测试工具，验证自动化服务是否正常运行。',
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
    tone: 'Ops Radar',
    summary: '连接指标看板、工作日历和渠道协同，形成清晰的运营节奏。',
    tools: [
      { id: 'metrics_hub', name: '指标中心', tag: 'Metrics', description: '集中展示关键指标和异常波动。' },
      { id: 'calendar_sync', name: '运营日历', tag: 'Calendar', description: '让重要节点和协作事项一目了然。' },
      { id: 'channel_map', name: '渠道地图', tag: 'Channel', description: '追踪渠道表现与协同状态。' },
    ],
  },
]
