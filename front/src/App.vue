<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getData, getToolConfig, getToolPreview, runDepartmentTool, saveConfig, getDepartmentConfig, saveDepartmentConfig, testNetworkPath } from './api/index'
import ExecutionLogPanel from './components/ExecutionLogPanel.vue'
import ToolPreviewDialog from './components/preview/ToolPreviewDialog.vue'
import UiBadge from './components/ui/UiBadge.vue'
import UiButton from './components/ui/UiButton.vue'
import UiCard from './components/ui/UiCard.vue'
import UiDialog from './components/ui/UiDialog.vue'
import UiFileInput from './components/ui/UiFileInput.vue'
import UiInput from './components/ui/UiInput.vue'
import UiLabel from './components/ui/UiLabel.vue'
import UiSelect from './components/ui/UiSelect.vue'
import UiToastStack from './components/ui/UiToastStack.vue'
import { departments } from './data/departments'
import GalaxyBackground from './components/GalaxyBackground.vue'
import { Sun, Moon, Monitor } from 'lucide-vue-next'

const PREVIEW_TOOL_ID = 'invoice_recognizer'
const PREVIEW_DEPARTMENT = 'CONSULT'

const STORAGE_KEY = 'yisi-auto-tool:department'

const getSavedDepartment = () => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && departments.some(d => d.code === saved)) {
      return saved
    }
  } catch {
    // localStorage 不可用，使用默认值
  }
  return departments[0].code
}

// Theme logic
const THEME_STORAGE_KEY = 'yisi-auto-tool:theme'
const themeMode = ref('system') // 'light', 'dark', 'system'

const getSavedTheme = () => {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY)
    if (saved && ['light', 'dark', 'system'].includes(saved)) {
      return saved
    }
  } catch {
    // localStorage 不可用
  }
  return 'system'
}

themeMode.value = getSavedTheme()

const isDark = computed(() => {
  if (themeMode.value === 'dark') return true
  if (themeMode.value === 'light') return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
})

const applyTheme = () => {
  const html = document.documentElement
  if (isDark.value) {
    html.setAttribute('data-theme', 'dark')
  } else {
    html.removeAttribute('data-theme')
  }
}

const cycleTheme = () => {
  const modes = ['light', 'dark', 'system']
  const currentIndex = modes.indexOf(themeMode.value)
  const nextIndex = (currentIndex + 1) % modes.length
  themeMode.value = modes[nextIndex]
  try {
    localStorage.setItem(THEME_STORAGE_KEY, themeMode.value)
  } catch {
    // localStorage 不可用
  }
  applyTheme()
}

const themeIcon = computed(() => {
  if (themeMode.value === 'dark') return Moon
  if (themeMode.value === 'light') return Sun
  return Monitor
})

const themeLabel = computed(() => {
  if (themeMode.value === 'dark') return '深色'
  if (themeMode.value === 'light') return '浅色'
  return '跟随系统'
})

const activeDepartmentCode = ref(getSavedDepartment())
const runningToolId = ref('')
const previewDialogOpen = ref(false)
const previewLoading = ref(false)
const previewData = ref(null)
const previewTargetKey = ref('')
const configDialogOpen = ref(false)
const toasts = ref([])
const logPanel = ref(null)

const lastUpdated = ref('等待同步')
const connectionStatus = ref({
  state: 'pending',
  label: '连接检查中',
  detail: '正在确认自动化服务是否可用。',
})

// 部门局域网配置
const departmentConfig = ref({
  networkPath: ''
})
const testingNetworkPath = ref(false)
const networkPathTestResult = ref(null)

const configData = ref({
  folderPath: '',
  listExcelPath: '',
  // BUE2 email extractor config
  email: '',
  authCode: '',
  maxEmails: 50,
  subjectKeyword: '注销成功',
  selectedFolder: '',  // 用户选择的邮箱文件夹(encoded)
})

const currentConfigTool = ref({ department: '', toolId: '' })
const mailFolders = ref([])
const loadingFolders = ref(false)
const mailFoldersError = ref('')
const showAuthCode = ref(false)

// 将mailFolders转换为UiSelect需要的options格式
const folderOptions = computed(() => {
  if (mailFolders.value.length === 0) {
    return [{ value: '', label: '请先输入邮箱和授权码', disabled: true }]
  }
  
  // 转换并排序：系统文件夹（蓝色）排在最前面
  const options = mailFolders.value.map(folder => {
    // 系统文件夹显示中文名称，其他显示解码后的名称
    const label = folder.type === 'inbox' ? '收件箱' :
                  folder.type === 'sent' ? '已发送' :
                  folder.type === 'drafts' ? '草稿箱' :
                  folder.type === 'trash' ? '垃圾桶' :
                  folder.display
    return {
      value: folder.encoded,
      label: label,
      type: folder.type,
      badge: null // 不再单独显示badge，直接作为label
    }
  })
  
  // 排序：系统文件夹(type !== 'other')排在前面，然后按名称排序
  return options.sort((a, b) => {
    const aIsSystem = a.type !== 'other'
    const bIsSystem = b.type !== 'other'
    
    if (aIsSystem && !bIsSystem) return -1
    if (!aIsSystem && bIsSystem) return 1
    
    // 同类型按名称排序
    return a.label.localeCompare(b.label, 'zh-CN')
  })
})

const previewCache = new Map()
let previewAbortController = null
const toastTimers = new Map()

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

const configuredSummary = computed(() => {
  const config = configData.value

  // Check CONSULT config
  const hasFolder = Boolean(config.folderPath)
  if (activeDepartmentCode.value === 'CONSULT' && hasFolder) {
    return '已配置完成'
  }

  // Check BUE2 config
  const hasEmail = Boolean(config.email && config.authCode)
  if (activeDepartmentCode.value === 'BUE2' && hasEmail) {
    return '已配置完成'
  }

  return '待配置'
})

const configDialogTitle = computed(() => {
  if (currentConfigTool.value.toolId === 'citeo_email_extractor') {
    return '邮箱配置'
  }
  return '英德单据识别配置'
})

const configDialogDescription = computed(() => {
  if (currentConfigTool.value.toolId === 'citeo_email_extractor') {
    return '163邮箱已配置，用于IMAP连接提取邮件。'
  }
  return ''
})

function getToolKey(departmentCode, toolId) {
  return `${departmentCode}:${toolId}`
}

function pushToast({ type = 'info', title, message = '', duration = 4200 }) {
  const id = `toast-${Date.now()}-${Math.random().toString(16).slice(2)}`
  toasts.value = [...toasts.value, { id, type, title, message }]

  if (duration > 0) {
    const timer = setTimeout(() => dismissToast(id), duration)
    toastTimers.set(id, timer)
  }
}

function dismissToast(id) {
  const timer = toastTimers.get(id)
  if (timer) {
    clearTimeout(timer)
    toastTimers.delete(id)
  }

  toasts.value = toasts.value.filter((toast) => toast.id !== id)
}

function clearPreviewRequest() {
  if (previewAbortController) {
    previewAbortController.abort()
    previewAbortController = null
  }
}

function getOutputSnippet(result) {
  return [result.stdout, result.stderr, result.error]
    .find((value) => typeof value === 'string' && value.trim())
    ?.trim()
    ?.slice(0, 180)
}

async function loadConnectionStatus() {
  lastUpdated.value = new Date().toLocaleString('zh-CN', { hour12: false })

  try {
    const response = await getData()
    connectionStatus.value = {
      state: 'online',
      label: '服务在线',
      detail: response.message || '自动化服务连接正常，预览与执行能力可用。',
    }
  } catch (error) {
    console.error(error)
    connectionStatus.value = {
      state: 'offline',
      label: '服务离线',
      detail: '未能连到后端服务，请确认 FastAPI 已启动且地址可访问。',
    }
  }
}

async function loadDepartmentConfig(department) {
  try {
    const response = await getDepartmentConfig(department)
    if (response?.success && response.config) {
      departmentConfig.value = {
        networkPath: response.config.networkPath || ''
      }
    }
  } catch (error) {
    console.error('Failed to load department config:', error)
  }
}

async function saveDepartmentConfiguration() {
  const dept = activeDepartmentCode.value
  try {
    const response = await saveDepartmentConfig(dept, {
      networkPath: departmentConfig.value.networkPath
    })
    if (response?.success) {
      pushToast({
        type: 'success',
        title: '部门配置已保存',
        message: '局域网路径已更新。',
      })
    } else {
      throw new Error(response?.error || '保存失败')
    }
  } catch (error) {
    console.error('Failed to save department config:', error)
    pushToast({
      type: 'error',
      title: '保存失败',
      message: error.message || '无法保存部门配置。',
    })
  }
}

async function testDeptNetworkPath() {
  const path = departmentConfig.value.networkPath
  if (!path) {
    networkPathTestResult.value = { success: false, message: '请先输入网络路径' }
    return
  }

  testingNetworkPath.value = true
  networkPathTestResult.value = null

  try {
    const response = await testNetworkPath(path)
    networkPathTestResult.value = {
      success: response?.success,
      message: response?.message || response?.error || '测试完成'
    }
    if (response?.success) {
      pushToast({
        type: 'success',
        title: '连接成功',
        message: '网络路径可正常访问。',
      })
    }
  } catch (error) {
    networkPathTestResult.value = {
      success: false,
      message: error.message || '网络请求失败'
    }
  } finally {
    testingNetworkPath.value = false
  }
}

async function loadToolConfig(department, toolId) {
  try {
    const response = await getToolConfig(department, toolId)
    if (response?.success && response.config) {
      const cfg = response.config
      // Merge with defaults
      configData.value = {
        folderPath: cfg.folderPath || '',
        listExcelPath: cfg.listExcelPath || '',
        email: cfg.email || '',
        authCode: cfg.authCode || '',
        maxEmails: cfg.maxEmails || 50,
        subjectKeyword: cfg.subjectKeyword || '注销成功',
        selectedFolder: cfg.selectedFolder || '',
      }
    }
  } catch (error) {
    console.error('Failed to load config:', error)
  }
}

// Legacy support
async function loadInvoiceConfig() {
  await loadToolConfig(PREVIEW_DEPARTMENT, PREVIEW_TOOL_ID)
}

function openConfigDialog(tool) {
  currentConfigTool.value = {
    department: activeDepartmentCode.value,
    toolId: tool.id,
  }
  mailFolders.value = []
  // Load config for this specific tool
  loadToolConfig(activeDepartmentCode.value, tool.id)
  configDialogOpen.value = true
  // If BUE2 tool, auto-load folders if credentials available
  if (tool.id === 'citeo_email_extractor') {
    nextTick(() => {
      if (configData.value.email && configData.value.authCode) {
        loadMailFolders()
      }
    })
  }
}

async function loadMailFolders() {
  const { email, authCode } = configData.value
  if (!email || !authCode) {
    return
  }

  loadingFolders.value = true
  mailFoldersError.value = ''
  try {
    const response = await fetch('/api/list-mail-folders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, authCode }),
    })

    const result = await response.json()
    if (result?.success && result.folders && result.folders.length > 0) {
      mailFolders.value = result.folders
      mailFoldersError.value = ''
      // Auto-select first inbox if none selected
      const inbox = result.folders.find(f => f.type === 'inbox')
      if (inbox && !configData.value.selectedFolder) {
        configData.value.selectedFolder = inbox.encoded
      }
    } else {
      mailFolders.value = []
      mailFoldersError.value = result?.error || '无法获取文件夹列表，请检查邮箱账号和授权码是否正确，以及IMAP服务是否已开启'
    }
  } catch (error) {
    mailFolders.value = []
    mailFoldersError.value = '网络请求失败，请检查网络连接'
  } finally {
    loadingFolders.value = false
  }
}

async function saveConfiguration() {
  const { department, toolId } = currentConfigTool.value
  const targetDept = department || PREVIEW_DEPARTMENT
  const targetTool = toolId || PREVIEW_TOOL_ID

  try {
    const response = await saveConfig(targetDept, targetTool, configData.value)
    if (!response?.success) {
      throw new Error(response?.error || '保存失败')
    }

    configDialogOpen.value = false
    pushToast({
      type: 'success',
      title: '配置已保存'
    })

    previewCache.delete(getToolKey(targetDept, targetTool))
    if (previewDialogOpen.value && previewTargetKey.value === getToolKey(targetDept, targetTool)) {
      await openToolPreview(findPreviewTool(), { force: true })
    }
  } catch (error) {
    console.error('Failed to save config:', error)
    pushToast({
      type: 'error',
      title: '保存失败',
      message: error.message || '请检查配置内容后重试。',
    })
  }
}

function findPreviewTool() {
  return departments
    .find((department) => department.code === PREVIEW_DEPARTMENT)
    ?.tools.find((tool) => tool.id === PREVIEW_TOOL_ID)
}

async function warmToolPreview(tool) {
  if (!tool?.previewable) {
    return
  }

  const key = getToolKey(activeDepartmentCode.value, tool.id)
  if (previewCache.has(key)) {
    return
  }

  try {
    const response = await getToolPreview(activeDepartmentCode.value, tool.id)
    if (response?.success && response.preview) {
      previewCache.set(key, response.preview)
    }
  } catch (error) {
    console.debug('Preview warm-up skipped:', error)
  }
}

async function openToolPreview(tool, options = {}) {
  if (!tool?.previewable) {
    pushToast({
      type: 'warning',
      title: '预览暂未开放',
      message: '当前仅对英德单据识别提供企业级预览能力。',
    })
    return
  }

  const force = options.force === true
  const toolKey = getToolKey(activeDepartmentCode.value, tool.id)
  previewTargetKey.value = toolKey
  previewDialogOpen.value = true
  previewData.value = previewCache.get(toolKey) ?? null

  if (!force && previewData.value) {
    previewLoading.value = false
    return
  }

  previewLoading.value = true

  clearPreviewRequest()
  await nextTick()
  await new Promise((resolve) => requestAnimationFrame(resolve))

  previewAbortController = new AbortController()

  try {
    const response = await getToolPreview(activeDepartmentCode.value, tool.id, previewAbortController.signal)
    if (!response?.success || !response.preview) {
      throw new Error(response?.error || '未能获取预览数据')
    }

    previewCache.set(toolKey, response.preview)
    if (previewTargetKey.value === toolKey) {
      previewData.value = response.preview
    }
  } catch (error) {
    if (error.name !== 'AbortError') {
      console.error('Failed to load preview:', error)
      if (previewTargetKey.value === toolKey) {
        previewData.value = null
      }
      pushToast({
        type: 'error',
        title: '预览加载失败',
        message: error.message || '请稍后重试。',
      })
    }
  } finally {
    previewAbortController = null
    if (previewTargetKey.value === toolKey) {
      previewLoading.value = false
    }
  }
}

async function refreshPreview() {
  const tool = findPreviewTool()
  if (!tool) {
    return
  }

  previewCache.delete(getToolKey(PREVIEW_DEPARTMENT, PREVIEW_TOOL_ID))
  await openToolPreview(tool, { force: true })
}

async function runDepartmentScript(tool) {
  if (tool.action !== 'run_script') {
    return
  }

  runningToolId.value = tool.id
  let isBackgroundTask = false

  try {
    const result = await runDepartmentTool(activeDepartmentCode.value, tool.id)

    if (result?.success && result?.status === 'running') {
      // 任务已启动，正在后台运行
      isBackgroundTask = true
      pushToast({
        type: 'info',
        title: '任务已启动',
        message: `${tool.name} 正在后台运行，请查看右侧执行记录。`,
        duration: 3000,
      })
      // 立即标记任务启动，确保能检测到完成状态
      logPanel.value?.onTaskStarted()
      // 刷新日志显示运行中的任务
      console.log('Refreshing log panel after run...', logPanel.value)
      setTimeout(async () => {
        await logPanel.value?.refresh()
        console.log('Log panel refreshed')
      }, 200)
      // 后台任务不清空runningToolId，等执行记录组件反馈完成状态
      return
    }

    const summary = getOutputSnippet(result)

    if (result?.success) {
      pushToast({
        type: 'success',
        title: '脚本执行成功',
        message: summary || '识别任务已完成。',
        duration: 5200,
      })
      return
    }

    pushToast({
      type: 'error',
      title: '脚本执行失败',
      message: summary || '请查看控制台或后端日志定位原因。',
      duration: 5200,
    })
  } catch (error) {
    console.error('Failed to run script:', error)
    pushToast({
      type: 'error',
      title: '执行请求失败',
      message: '请确认 FastAPI 服务已启动，例如 `uvicorn main:app --reload`。',
      duration: 5200,
    })
  } finally {
    if (!isBackgroundTask) {
      runningToolId.value = ''
    }
  }
}

watch(activeDepartmentCode, async (departmentCode) => {
  try {
    localStorage.setItem(STORAGE_KEY, departmentCode)
  } catch {
    // localStorage 不可用，静默处理
  }
  if (departmentCode === PREVIEW_DEPARTMENT) {
    const tool = findPreviewTool()
    await warmToolPreview(tool)
  }
})

watch(previewDialogOpen, (open) => {
  if (!open) {
    clearPreviewRequest()
    previewLoading.value = false
  }
})

onMounted(async () => {
  await Promise.all([loadConnectionStatus(), loadInvoiceConfig()])
  await warmToolPreview(findPreviewTool())
  // 加载当前部门配置
  await loadDepartmentConfig(activeDepartmentCode.value)
  // Apply initial theme
  applyTheme()
  // Listen for system theme changes
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme)
})

// 监听部门切换，加载对应配置
watch(activeDepartmentCode, async (newDept) => {
  await loadDepartmentConfig(newDept)
  // 清空测试结果
  networkPathTestResult.value = null
})

onBeforeUnmount(() => {
  clearPreviewRequest()
  for (const timer of toastTimers.values()) {
    clearTimeout(timer)
  }
  toastTimers.clear()
})
</script>

<template>
  <div class="page-shell">
    <GalaxyBackground
      :mouse-repulsion="true"
      :mouse-interaction="true"
      :density="0.88"
      :glow-intensity="0.18"
      :saturation="0"
      :hue-shift="0"
      :twinkle-intensity="0.12"
      :rotation-speed="0.04"
      :repulsion-strength="1.2"
      :auto-center-repulsion="0"
      :star-speed="0.28"
      :speed="0.72"
      :transparent="true"
      v-if="isDark"
    />
    <header class="page-header">
      <div class="page-copy">
        <UiBadge variant="secondary">Department Workspace</UiBadge>
        <h1>部门工具工作台</h1>
      </div>

      <div class="header-actions">
        <UiButton variant="outline" class="theme-toggle" @click="cycleTheme">
          <component :is="themeIcon" :size="16" />
          <span>{{ themeLabel }}</span>
        </UiButton>
      </div>

      <UiCard class="status-panel">
        <div class="status-top">
          <UiBadge :variant="statusBadgeVariant">{{ connectionStatus.label }}</UiBadge>
          <p class="status-detail">{{ connectionStatus.detail }}</p>
        </div>
        <div class="status-meta">
          <div>
            <span>部门数量</span>
            <strong>{{ departments.length }}</strong>
          </div>
          <div>
            <span>工具总数</span>
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
        </div>

        <!-- 部门局域网路径配置 -->
        <div class="department-config-section">
          <div class="config-row">
            <div class="config-field">
              <UiLabel for="network-path">部门局域网路径</UiLabel>
              <UiInput
                id="network-path"
                v-model="departmentConfig.networkPath"
                placeholder="\\服务器\共享文件夹\部门路径(\\192.168.76.93\厦门部门\BUE2)"
              />
            </div>
            <div class="config-actions">
              <UiButton
                variant="outline"
                :loading="testingNetworkPath"
                @click="testDeptNetworkPath"
              >
                测试连接
              </UiButton>
              <UiButton @click="saveDepartmentConfiguration">
                保存配置
              </UiButton>
            </div>
          </div>
          <div v-if="networkPathTestResult" class="test-result" :class="{ success: networkPathTestResult.success, error: !networkPathTestResult.success }">
            {{ networkPathTestResult.message }}
          </div>
        </div>

        <div class="tool-grid">
          <UiCard
            v-for="tool in activeDepartment.tools"
            :key="tool.id"
            class="tool-card"
            tone="muted"
          >
            <div class="tool-card-head">
              <UiBadge variant="secondary">{{ tool.tag }}</UiBadge>
              <UiBadge variant="outline">
                {{ tool.previewable ? 'Preview Ready' : 'Roadmap' }}
              </UiBadge>
            </div>
            <div class="tool-card-body">
              <h3>{{ tool.name }}</h3>
              <p>{{ tool.description }}</p>
            </div>
            <div class="tool-card-foot">
              <template v-if="tool.previewable">
                <div class="tool-card-actions">
                  <UiButton
                    variant="outline"
                    @mouseenter="warmToolPreview(tool)"
                    @focus="warmToolPreview(tool)"
                    @click="openToolPreview(tool)"
                  >
                    预览
                  </UiButton>
                  <UiButton v-if="tool.configurable" variant="outline" @click="openConfigDialog(tool)">
                    配置
                  </UiButton>
                </div>
                <UiButton
                  :loading="runningToolId === tool.id"
                  @click="runDepartmentScript(tool)"
                >
                  运行识别
                </UiButton>
              </template>

              <template v-else-if="tool.action === 'run_script'">
                <UiButton
                  v-if="tool.configurable"
                  variant="outline"
                  style="margin-right: auto;"
                  @click="openConfigDialog(tool)"
                >
                  配置
                </UiButton>
                <UiButton
                  :loading="runningToolId === tool.id"
                  @click="runDepartmentScript(tool)"
                >
                  {{ runningToolId === tool.id ? '运行中' : '运行' }}
                </UiButton>
              </template>

              <template v-else>
                <UiButton variant="outline" disabled>预览建设中</UiButton>
                <UiButton disabled>能力建设中</UiButton>
              </template>
            </div>
          </UiCard>
        </div>
      </UiCard>

      <UiCard class="aside-card">
        <ExecutionLogPanel 
          ref="logPanel"
          :department="activeDepartment.code"
          :limit="10"
          @task-complete="runningToolId = ''"
        />
      </UiCard>
    </section>

    <ToolPreviewDialog
      v-model:open="previewDialogOpen"
      :loading="previewLoading"
      :preview="previewData"
      @refresh="refreshPreview"
    />

    <UiDialog
      v-model:open="configDialogOpen"
      keep-mounted
      :title="configDialogTitle"
      :description="configDialogDescription"
    >
      <!-- CONSULT Invoice Recognizer Config -->
      <div v-if="currentConfigTool.toolId !== 'citeo_email_extractor'" class="config-form">
        <div class="form-field">
          <UiLabel for="folder-path">选择递延数据所在总文件夹路径</UiLabel>
          <UiFileInput
            id="folder-path"
            v-model="configData.folderPath"
            placeholder="总文件夹/客户号文件夹/pdf"
            webkitdirectory
          />
        </div>

        <div class="form-field">
          <UiLabel for="list-excel-path">选择 Excel 清单文件</UiLabel>
          <UiFileInput
            id="list-excel-path"
            v-model="configData.listExcelPath"
            placeholder="选择包含单据清单的 Excel 文件..."
            accept=".xlsx,.xls"
          />
        </div>
      </div>

      <!-- BUE2 Email Extractor Config -->
      <div v-else class="config-form">
        <div class="form-field">
          <UiLabel for="email">163邮箱账号</UiLabel>
          <UiInput
            id="email"
            v-model="configData.email"
            type="email"
            placeholder="your_email@163.com"
            disabled
          />
        </div>

        <div class="form-field">
          <small class="field-hint">提示：点击加载文件夹---选择存放注销邮箱的文件夹---填写获取邮件数量(可自行前往163查看对应文件夹数量有多少)---保存配置即可运行。邮箱和授权码已预配置。如需更改联系管理员</small>
        </div>

        <div class="form-field">
          <div class="folder-select-header">
            <UiLabel for="mail-folder">选择邮件文件夹(存放注销邮件的文件夹)</UiLabel>
            <UiButton
              variant="outline"
              size="sm"
              :loading="loadingFolders"
              :disabled="!configData.email"
              @click="loadMailFolders"
            >
              {{ mailFolders.length > 0 ? '刷新' : '加载文件夹' }}
            </UiButton>
          </div>
          <UiSelect
            id="mail-folder"
            v-model="configData.selectedFolder"
            :disabled="mailFolders.length === 0"
            :options="folderOptions"
            placeholder="请选择文件夹"
            :searchable="false"
          />
          <small v-if="mailFoldersError" class="field-error">{{ mailFoldersError }}</small>
        </div>

        <div class="form-field">
          <UiLabel for="max-emails">邮件数量限制</UiLabel>
          <UiInput
            id="max-emails"
            v-model="configData.maxEmails"
            type="number"
            placeholder="50"
          />
        </div>
      </div>

      <template #footer>
        <UiButton variant="outline" @click="configDialogOpen = false">取消</UiButton>
        <UiButton @click="saveConfiguration">保存配置</UiButton>
      </template>
    </UiDialog>

    <UiToastStack class="page-toast-stack" :toasts="toasts" @dismiss="dismissToast" />
  </div>
</template>

<style scoped>
/* Page shell with Galaxy background */
.page-shell {
  position: relative;
  min-height: 100vh;
  padding: 1.5rem;
}

.page-shell > *:not(.galaxy-container):not(.page-toast-stack) {
  position: relative;
  z-index: 1;
}

/* Header actions for theme toggle */
.header-actions {
  position: absolute;
  top: 1.5rem;
  right: 1.5rem;
  z-index: 10;
}

.theme-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 0.8rem;
}

.theme-toggle span {
  min-width: 4em;
  text-align: center;
}

/* 部门局域网路径配置样式 */
.department-config-section {
  margin: 1.5rem 0;
  padding: 1rem;
  background: var(--card-muted);
  border-radius: 8px;
  border: 1px solid var(--border);
}

.config-row {
  display: flex;
  align-items: flex-end;
  gap: 1rem;
}

.config-field {
  flex: 1;
}

.config-actions {
  display: flex;
  gap: 0.5rem;
}

.test-result {
  margin-top: 0.75rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  font-size: 0.875rem;
  border: 1px solid transparent;
}

.test-result.success {
  background: var(--success-soft);
  border-color: var(--success-border);
  color: var(--success);
}

.test-result.error {
  background: var(--danger-soft);
  border-color: var(--danger-border);
  color: var(--danger);
}

.field-hint {
  display: block;
  margin-top: 0.25rem;
  font-size: 0.75rem;
  color: var(--muted);
}

.field-error {
  display: block;
  margin-top: 0.25rem;
  font-size: 0.75rem;
  color: var(--danger);
}

.folder-select-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.input-with-action {
  display: flex;
  gap: 0.5rem;
  align-items: stretch;
}

.input-with-button {
  flex: 1;
}

.toggle-visibility-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--card);
  cursor: pointer;
  color: var(--muted);
  transition: all 0.15s ease;
}

.toggle-visibility-icon:hover {
  border-color: var(--border-strong);
  color: var(--foreground);
}

.toggle-visibility-icon:active {
  background: var(--card-muted);
}
</style>
