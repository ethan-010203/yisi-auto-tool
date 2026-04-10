<script setup>
import { computed, onMounted, ref } from 'vue'
import { getData } from './api/index'
import UiBadge from './components/ui/UiBadge.vue'
import UiButton from './components/ui/UiButton.vue'
import UiCard from './components/ui/UiCard.vue'

const lastUpdated = ref('等待同步')
const connectionStatus = ref({
  state: 'pending',
  label: '接口检查中',
  detail: '正在连接本地服务',
})

const departments = [
  {
    code: 'BUE1',
    name: 'BUE1',
    tone: '客户推进',
    summary: '销售前线工具入口，适合线索跟进、客户推进与阶段记录。',
    tools: [
      { name: '商机总览', tag: 'Pipeline', description: '集中查看重点客户、机会状态与负责人。' },
      { name: '线索池', tag: 'Leads', description: '统一沉淀新增线索、分级意向和来源渠道。' },
      { name: '拜访纪要', tag: 'Notes', description: '管理销售沟通纪要与下一步动作。' },
    ],
  },
  {
    code: 'BUE2',
    name: 'BUE2',
    tone: '方案交付',
    summary: '方案与交付协同入口，适合报价、排期和项目推进。',
    tools: [
      { name: '项目排期', tag: 'Schedule', description: '同步项目节点、里程碑和内部协作进度。' },
      { name: '报价模板', tag: 'Quote', description: '快速访问标准化报价与成本测算文件。' },
      { name: '复盘档案', tag: 'Review', description: '沉淀项目结果、复盘结论与经验记录。' },
    ],
  },
  {
    code: 'BUE3',
    name: 'BUE3',
    tone: '协同管理',
    summary: '跨团队协作入口，适合任务统筹、资源共享与透明管理。',
    tools: [
      { name: '区域日报', tag: 'Daily', description: '查看每日推进情况、异常事项和同步重点。' },
      { name: '任务看板', tag: 'Board', description: '统一追踪责任人、进度与优先级变化。' },
      { name: '资源共享', tag: 'Assets', description: '沉淀跨组资料、模板与通用支持文件。' },
    ],
  },
  {
    code: 'BUV1',
    name: 'BUV1',
    tone: '内容生产',
    summary: '内容制作入口，适合选题规划、素材整理和发布协作。',
    tools: [
      { name: '选题日历', tag: 'Plan', description: '管理月度选题、版本节奏与发布时间。' },
      { name: '素材库', tag: 'Media', description: '集中存放文案、封面、脚本和原始素材。' },
      { name: '发布检查', tag: 'Publish', description: '统一核对发布前的配置、标题和说明文案。' },
    ],
  },
  {
    code: 'BUV2',
    name: 'BUV2',
    tone: '增长执行',
    summary: '增长支持入口，适合直播、投放和活动反馈管理。',
    tools: [
      { name: '直播排班', tag: 'Roster', description: '查看场次安排、岗位分配与值守节奏。' },
      { name: '投放监测', tag: 'Ads', description: '关注投放表现、预算消耗与核心指标波动。' },
      { name: '复盘报告', tag: 'Report', description: '沉淀活动结果、亮点问题与优化动作。' },
    ],
  },
  {
    code: 'BUV3',
    name: 'BUV3',
    tone: '品牌创意',
    summary: '品牌创意入口，适合策划提案、创意输出和视觉规范查阅。',
    tools: [
      { name: 'Campaign Board', tag: 'Brand', description: '管理品牌活动节奏、主题与执行节点。' },
      { name: '创意提案', tag: 'Idea', description: '集中查看提案版本、评审意见与修改方向。' },
      { name: '视觉规范', tag: 'Guide', description: '统一访问品牌视觉要求与设计资产。' },
    ],
  },
  {
    code: 'CONSULT',
    name: '顾问部',
    tone: '咨询支持',
    summary: '咨询策略入口，适合知识沉淀、客户方案与会议记录。',
    tools: [
      { name: '咨询知识库', tag: 'Knowledge', description: '汇总方法论、经典案例和常见问题解法。' },
      { name: '方案模板', tag: 'Template', description: '快速进入标准方案结构与交付模板。' },
      { name: '客户纪要', tag: 'Client', description: '沉淀关键会议纪要、待办事项和客户反馈。' },
    ],
  },
  {
    code: 'OPS',
    name: '运营部',
    tone: '运营统筹',
    summary: '运营管理入口，适合数据监控、活动安排与渠道管理。',
    tools: [
      { name: '数据日报', tag: 'Metrics', description: '快速查看核心经营指标与趋势变化。' },
      { name: '活动日历', tag: 'Calendar', description: '掌握近期活动、节点提醒与协同安排。' },
      { name: '渠道监控', tag: 'Channel', description: '跟踪各渠道状态、异常波动和告警信息。' },
    ],
  },
]

const activeDepartmentCode = ref(departments[0].code)

const activeDepartment = computed(() => {
  return departments.find((department) => department.code === activeDepartmentCode.value) ?? departments[0]
})

const totalTools = computed(() => {
  return departments.reduce((count, department) => count + department.tools.length, 0)
})

const statusBadgeVariant = computed(() => {
  if (connectionStatus.value.state === 'online') {
    return 'success'
  }

  if (connectionStatus.value.state === 'offline') {
    return 'warning'
  }

  return 'secondary'
})

onMounted(async () => {
  lastUpdated.value = new Date().toLocaleString('zh-CN', { hour12: false })

  try {
    const response = await getData()
    connectionStatus.value = {
      state: 'online',
      label: '接口连接正常',
      detail: response.message || '已收到本地服务返回结果',
    }
  } catch (error) {
    console.error(error)
    connectionStatus.value = {
      state: 'offline',
      label: '接口暂不可用',
      detail: '页面结构可先使用，后续补入真实工具链接即可。',
    }
  }
})
</script>

<template>
  <div class="page-shell">
    <header class="page-header">
      <div class="page-copy">
        <UiBadge variant="secondary">Department Workspace</UiBadge>
        <h1>公司部门工具台</h1>
      </div>

      <UiCard class="status-panel">
        <div class="status-top">
          <UiBadge :variant="statusBadgeVariant">{{ connectionStatus.label }}</UiBadge>
          <p class="status-detail">{{ connectionStatus.detail }}</p>
        </div>
        <div class="status-meta">
          <div>
            <span>部门数</span>
            <strong>{{ departments.length }}</strong>
          </div>
          <div>
            <span>工具位</span>
            <strong>{{ totalTools }}</strong>
          </div>
          <div>
            <span>最近同步</span>
            <strong>{{ lastUpdated }}</strong>
          </div>
        </div>
      </UiCard>
    </header>

    <UiCard class="tabs-card">
      <div class="tabs-head">
        <div>
          <p class="section-label">Departments</p>
          <h2>部门切换</h2>
        </div>
        <p class="section-note">点击标签查看当前部门工具，结构上参考 `Tabs + Card + Badge + Button`。</p>
      </div>

      <div class="tabs-list" role="tablist" aria-label="部门切换">
        <button
          v-for="department in departments"
          :key="department.code"
          type="button"
          class="tab-trigger"
          :class="{ active: department.code === activeDepartmentCode }"
          :aria-selected="department.code === activeDepartmentCode"
          @click="activeDepartmentCode = department.code"
        >
          <span>{{ department.name }}</span>
          <small>{{ department.tone }}</small>
        </button>
      </div>
    </UiCard>

    <section class="content-grid">
      <UiCard class="department-card">
        <div class="department-header">
          <div class="department-copy">
            <div class="department-badges">
              <UiBadge>{{ activeDepartment.code }}</UiBadge>
              <UiBadge variant="secondary">{{ activeDepartment.tone }}</UiBadge>
            </div>
            <h2>{{ activeDepartment.name }}</h2>
            <p>{{ activeDepartment.summary }}</p>
          </div>

          <div class="department-actions">
            <UiButton>新增工具入口</UiButton>
            <UiButton variant="outline">编辑部门配置</UiButton>
          </div>
        </div>

        <div class="tool-grid">
          <UiCard
            v-for="tool in activeDepartment.tools"
            :key="tool.name"
            class="tool-card"
            tone="muted"
          >
            <div class="tool-card-head">
              <UiBadge variant="secondary">{{ tool.tag }}</UiBadge>
              <UiBadge variant="outline">待接入</UiBadge>
            </div>
            <div class="tool-card-body">
              <h3>{{ tool.name }}</h3>
              <p>{{ tool.description }}</p>
            </div>
            <div class="tool-card-foot">
              <UiButton variant="outline">查看详情</UiButton>
              <UiButton>配置入口</UiButton>
            </div>
          </UiCard>
        </div>
      </UiCard>

      <UiCard class="aside-card">
        <div class="aside-block">
          <p class="section-label">Current Focus</p>
          <h3>当前部门信息</h3>
          <ul class="info-list">
            <li>
              <span>部门代码</span>
              <strong>{{ activeDepartment.code }}</strong>
            </li>
            <li>
              <span>定位标签</span>
              <strong>{{ activeDepartment.tone }}</strong>
            </li>
            <li>
              <span>工具数量</span>
              <strong>{{ activeDepartment.tools.length }}</strong>
            </li>
          </ul>
        </div>

        <div class="aside-block">
          <p class="section-label">Design Notes</p>
          <h3>这次的样式方向</h3>
          <p class="aside-text">
            以浅色中性背景、细边框、轻投影和紧凑组件为主，减少花哨装饰，让内容更像真正可扩展的内部产品页面。
          </p>
        </div>
      </UiCard>
    </section>
  </div>
</template>
