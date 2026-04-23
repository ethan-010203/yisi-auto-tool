<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getData, getToolConfig, getToolPreview, getToolTemplateUrl, listMailFolders, runDepartmentTool, saveConfig, getDepartmentConfig, saveDepartmentConfig, testNetworkPath } from './api/index'
import ExecutionLogPanel from './components/ExecutionLogPanel.vue'
import GlobalRunningTasksBar from './components/GlobalRunningTasksBar.vue'
import ToolPreviewDialog from './components/preview/ToolPreviewDialog.vue'
import UiBadge from './components/ui/UiBadge.vue'
import UiButton from './components/ui/UiButton.vue'
import UiCard from './components/ui/UiCard.vue'
import UiDialog from './components/ui/UiDialog.vue'
import UiInput from './components/ui/UiInput.vue'
import UiLabel from './components/ui/UiLabel.vue'
import UiSelect from './components/ui/UiSelect.vue'
import UiToastStack from './components/ui/UiToastStack.vue'
import { departments } from './data/departments'

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
    // localStorage 不可用时回退到默认部门
  }
  return departments[0].code
}

const activeDepartmentCode = ref(getSavedDepartment())
const activeToolIdsByDepartment = ref({})
const previewDialogOpen = ref(false)
const previewLoading = ref(false)
const previewData = ref(null)
const previewTargetKey = ref('')
const configDialogOpen = ref(false)
const configPanelOpen = ref(false)
const toolConfigCache = ref({})
const toasts = ref([])
const logPanel = ref(null)
const globalRunningBar = ref(null)

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
const NETWORK_REQUIRED_TOOL_KEYS = new Set([
  'CONSULT:invoice_recognizer',
])

const createDefaultConfigData = () => ({
  folderPath: '',
  folderDisplay: '',
  excelPath: '',
  listExcelPath: '',
  listExcelDisplay: '',
  excelFilePath: '',
  excelFileDisplay: '',
  excelFolderPath: '',
  excelFolderDisplay: '',
  reportYear: '',
  reportMonthGerman: '',
  // BUE2 email extractor config
  email: '',
  authCode: '',
  maxEmails: 50,
  subjectKeyword: '注销成功',
  selectedFolder: '',
})
const configData = ref(createDefaultConfigData())

const currentConfigTool = ref({ department: '', toolId: '' })
const mailFolders = ref([])
const loadingFolders = ref(false)
const mailFoldersError = ref('')
const loadingToolConfig = ref(false)
const savingToolConfig = ref(false)
const savingDepartmentConfig = ref(false)
const pendingToolKeys = ref({})

// 将邮件文件夹列表转换为 UiSelect 需要的 options 格式
const folderOptions = computed(() => {
  if (mailFolders.value.length === 0) {
    return [{ value: '', label: '请先输入邮箱和授权码', disabled: true }]
  }

  const options = mailFolders.value.map(folder => {
    const label = folder.type === 'inbox' ? '收件箱' :
                  folder.type === 'sent' ? '已发送' :
                  folder.type === 'drafts' ? '草稿箱' :
                  folder.type === 'trash' ? '垃圾箱' :
                  folder.display
    return {
      value: folder.encoded,
      label: label,
      type: folder.type,
      badge: null
    }
  })

  return options.sort((a, b) => {
    const aIsSystem = a.type !== 'other'
    const bIsSystem = b.type !== 'other'

    if (aIsSystem && !bIsSystem) return -1
    if (!aIsSystem && bIsSystem) return 1

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

const activeToolCount = computed(() => {
  return activeDepartment.value.tools.length
})

const activeRunningToolCount = computed(() => {
  return getDepartmentActiveToolIds(activeDepartmentCode.value).length
})

const normalizedDepartmentNetworkPath = computed(() => {
  return sanitizePathInput(departmentConfig.value.networkPath)
})

const networkPathBadgeVariant = computed(() => {
  if (networkPathTestResult.value?.success) {
    return 'success'
  }
  if (networkPathTestResult.value && !networkPathTestResult.value.success) {
    return 'warning'
  }
  if (normalizedDepartmentNetworkPath.value) {
    return 'secondary'
  }
  return 'outline'
})

const networkPathStatusLabel = computed(() => {
  if (networkPathTestResult.value?.success) {
    return '路径已验证'
  }
  if (networkPathTestResult.value && !networkPathTestResult.value.success) {
    return '验证失败'
  }
  if (normalizedDepartmentNetworkPath.value) {
    return '已填写待验证'
  }
  return '尚未配置'
})

const configPanelToggleLabel = computed(() => {
  if (configPanelOpen.value) {
    return '收起共享路径'
  }
  return normalizedDepartmentNetworkPath.value ? '编辑共享路径' : '配置共享路径'
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

const configDialogTitle = computed(() => {
  if (currentConfigTool.value.toolId === 'citeo_email_extractor') {
    return '邮箱配置'
  }
  return '英德单据识别配置'
})

const configDialogDescription = computed(() => {
  if (currentConfigTool.value.toolId === 'citeo_email_extractor') {
    return '163邮箱已配置，用于 IMAP 连接提取邮件。'
  }
  return ''
})

const activeConfigDialogTitle = computed(() => {
  if (currentConfigTool.value.toolId === 'ear_declaration_data_fetcher') {
    return 'EAR 抓取配置'
  }
  return configDialogTitle.value
})

const activeConfigDialogDescription = computed(() => {
  if (currentConfigTool.value.toolId === 'ear_declaration_data_fetcher') {
    return '填写申报数据 Excel 文件路径，并配置检测年份和德语月份；EAR 官网账号和密码将从表格列中读取。'
  }
  return configDialogDescription.value
})

function getCachedToolConfig(departmentCode, toolId) {
  return toolConfigCache.value[getToolKey(departmentCode, toolId)] || null
}

function hasSavedToolConfig(departmentCode, toolId) {
  const config = getCachedToolConfig(departmentCode, toolId)
  if (!config) {
    return false
  }

  if (toolId === 'invoice_recognizer') {
    const folderPath = sanitizePathInput(config.folderPath || config.folderDisplay || '')
    const excelPath = sanitizePathInput(config.listExcelPath || config.excelPath || config.listExcelDisplay || '')
    return Boolean(folderPath && excelPath)
  }

  if (toolId === 'ear_declaration_data_fetcher') {
    const excelFilePath = sanitizePathInput(config.excelFilePath || config.excelFolderPath || '')
    const reportYear = String(config.reportYear || '').trim()
    const reportMonthGerman = String(config.reportMonthGerman || '').trim()
    return Boolean(excelFilePath && reportYear && reportMonthGerman)
  }

  if (toolId === 'citeo_email_extractor') {
    const selectedFolder = String(config.selectedFolder || '').trim()
    return Boolean(selectedFolder)
  }

  return true
}

function getToolSetupState(departmentCode, tool) {
  if (tool.action !== 'run_script') {
    return {
      key: 'coming-soon',
      label: '建设中',
      variant: 'secondary',
      description: '当前能力还在搭建中，暂时不可执行。',
      primaryLabel: '建设中',
      primaryAction: 'noop',
      primaryDisabled: true,
    }
  }

  if (isToolBusy(departmentCode, tool.id)) {
    return {
      key: 'running',
      label: '运行中',
      variant: 'warning',
      description: '任务已在后台运行，可以在右侧查看进度。',
      primaryLabel: '查看进度',
      primaryAction: 'focus-log',
      primaryDisabled: false,
    }
  }

  if (toolRequiresNetworkPath(departmentCode, tool.id) && !normalizedDepartmentNetworkPath.value) {
    return {
      key: 'needs-path',
      label: '待配置目录',
      variant: 'warning',
      description: '先完成部门共享目录配置和验证，再运行这个任务。',
      primaryLabel: '配置目录',
      primaryAction: 'open-path',
      primaryDisabled: false,
    }
  }

  if (tool.configurable && !hasSavedToolConfig(departmentCode, tool.id)) {
    return {
      key: 'needs-config',
      label: '待配置',
      variant: 'outline',
      description: '先补齐运行所需参数，这样使用时不会半路卡住。',
      primaryLabel: '先配置',
      primaryAction: 'open-config',
      primaryDisabled: false,
    }
  }

  return {
    key: 'ready',
    label: '可直接执行',
    variant: 'success',
    description: tool.previewable
      ? '配置已就绪，可先预览再启动任务。'
      : '当前配置已就绪，可以直接启动。',
    primaryLabel: '立即运行',
    primaryAction: 'run',
    primaryDisabled: false,
  }
}

const activeDepartmentNeedsNetworkPath = computed(() => {
  return activeDepartment.value.tools.some((tool) => toolRequiresNetworkPath(activeDepartmentCode.value, tool.id))
})

const activeReadyToolCount = computed(() => {
  return activeDepartment.value.tools.filter((tool) => getToolSetupState(activeDepartmentCode.value, tool).key === 'ready').length
})

const activeConfiguredToolCount = computed(() => {
  return activeDepartment.value.tools.filter((tool) => !tool.configurable || hasSavedToolConfig(activeDepartmentCode.value, tool.id)).length
})

const activeDepartmentStatus = computed(() => {
  if (connectionStatus.value.state === 'offline') {
    return {
      label: '服务待恢复',
      variant: 'warning',
      description: '后端服务暂时不可用，建议先确认 FastAPI 服务状态。',
    }
  }

  if (activeRunningToolCount.value > 0) {
    return {
      label: '有任务在跑',
      variant: 'warning',
      description: '当前部门已有任务在后台执行，可以直接查看记录或继续启动其他任务。',
    }
  }

  if (activeDepartmentNeedsNetworkPath.value && !normalizedDepartmentNetworkPath.value) {
    return {
      label: '先配置目录',
      variant: 'warning',
      description: '这个部门的核心任务依赖共享目录，先把目录配好会顺手很多。',
    }
  }

  if (activeReadyToolCount.value === 0) {
    return {
      label: '待准备',
      variant: 'secondary',
      description: '首选补全工具配置，让常用任务可以一键启动。',
    }
  }

  return {
    label: '已就绪',
    variant: 'success',
    description: '当前部门已基本就绪，可以直接从下面的任务卡片开始执行。',
  }
})

const activeDepartmentOverview = computed(() => {
  return [
    {
      label: '可直接执行',
      value: `${activeReadyToolCount.value}/${activeToolCount.value}`,
      hint: activeReadyToolCount.value > 0 ? '已就绪' : '需先准备',
    },
    {
      label: '已完成配置',
      value: `${activeConfiguredToolCount.value}/${activeToolCount.value}`,
      hint: '含默认无需配置的任务',
    },
    {
      label: '后台运行',
      value: String(activeRunningToolCount.value),
      hint: activeRunningToolCount.value > 0 ? '正在处理' : '当前空闲',
    },
    {
      label: '最近同步',
      value: lastUpdated.value,
      hint: connectionStatus.value.label,
    },
  ]
})

const activeToolCards = computed(() => {
  return activeDepartment.value.tools.map((tool) => ({
    ...tool,
    setupState: getToolSetupState(activeDepartmentCode.value, tool),
  }))
})

function getToolKey(departmentCode, toolId) {
  return `${departmentCode}:${toolId}`
}

function toolRequiresNetworkPath(departmentCode, toolId) {
  return NETWORK_REQUIRED_TOOL_KEYS.has(getToolKey(departmentCode, toolId))
}

function cacheToolConfig(departmentCode, toolId, config) {
  toolConfigCache.value = {
    ...toolConfigCache.value,
    [getToolKey(departmentCode, toolId)]: {
      ...config,
    },
  }
}

function sanitizePathInput(value) {
  const raw = String(value ?? '').trim()
  if (raw.length >= 2) {
    const firstChar = raw[0]
    const lastChar = raw[raw.length - 1]
    if ((firstChar === '"' && lastChar === '"') || (firstChar === "'" && lastChar === "'")) {
      return raw.slice(1, -1).trim()
    }
  }
  return raw
}

function normalizeInvoiceRecognizerConfig(config) {
  const folderPath = sanitizePathInput(config.folderPath || '')
  const listExcelPath = sanitizePathInput(config.listExcelPath || config.excelPath || '')

  return {
    ...config,
    folderPath,
    folderDisplay: folderPath,
    excelPath: listExcelPath,
    listExcelPath,
    listExcelDisplay: listExcelPath,
  }
}

function normalizeEarDeclarationFetcherConfig(config) {
  const excelFilePath = sanitizePathInput(config.excelFilePath || config.excelFolderPath || '')
  const reportYear = String(config.reportYear || '').trim()
  const reportMonthGerman = String(config.reportMonthGerman || '').trim()

  return {
    ...config,
    excelFilePath,
    excelFileDisplay: excelFilePath,
    excelFolderPath: excelFilePath,
    excelFolderDisplay: excelFilePath,
    reportYear,
    reportMonthGerman,
  }
}

function updateInvoiceFolderPath(value) {
  const normalizedValue = sanitizePathInput(value)
  configData.value.folderPath = normalizedValue
  configData.value.folderDisplay = normalizedValue
}

function updateInvoiceExcelPath(value) {
  const normalizedValue = sanitizePathInput(value)
  configData.value.listExcelPath = normalizedValue
  configData.value.excelPath = normalizedValue
  configData.value.listExcelDisplay = normalizedValue
}

function updateEarExcelFilePath(value) {
  const normalizedValue = sanitizePathInput(value)
  configData.value.excelFilePath = normalizedValue
  configData.value.excelFileDisplay = normalizedValue
  configData.value.excelFolderPath = normalizedValue
  configData.value.excelFolderDisplay = normalizedValue
}

function validateInvoiceRecognizerPathsOrThrow(config) {
  const folderPath = (config.folderPath || '').trim()
  const excelPath = (config.listExcelPath || config.excelPath || '').trim()

  if (!folderPath || !excelPath) {
    throw new Error('请先选择或填写单据文件夹和 Excel 路径。')
  }
  if (!excelPath.toLowerCase().endsWith('.xlsx')) {
    throw new Error('Excel 清单必须是 .xlsx 文件。')
  }
}

function validateInvoiceRecognizerManualPathsOrThrow(config) {
  const folderPath = sanitizePathInput(config.folderPath || '')
  const excelPath = sanitizePathInput(config.listExcelPath || config.excelPath || '')

  if (!folderPath || !excelPath) {
    throw new Error('请先手动填写单据文件夹和 Excel 的真实路径。')
  }
  if (!excelPath.toLowerCase().endsWith('.xlsx')) {
    throw new Error('Excel 清单必须是 .xlsx 文件。')
  }
}

function validateEarDeclarationFetcherConfigOrThrow(config) {
  const excelFilePath = sanitizePathInput(config.excelFilePath || config.excelFolderPath || '')
  const reportYear = String(config.reportYear || '').trim()
  const reportMonthGerman = String(config.reportMonthGerman || '').trim()

  if (!excelFilePath) {
    throw new Error('请先填写申报数据 Excel 文件路径。')
  }
  const lowerPath = excelFilePath.toLowerCase()
  if (!lowerPath.endsWith('.xlsx') && !lowerPath.endsWith('.xlsm')) {
    throw new Error('申报数据 Excel 必须是 .xlsx 或 .xlsm 文件。')
  }
  if (!reportYear) {
    throw new Error('请先填写检测年份。')
  }
  if (!reportMonthGerman) {
    throw new Error('请先填写德语月份。')
  }
}

function downloadEarTemplate() {
  try {
    const url = getToolTemplateUrl('BUE1', 'ear_declaration_data_fetcher')
    window.open(url, '_blank', 'noopener')
  } catch (error) {
    pushToast({
      type: 'error',
      title: '模板下载失败',
      message: error?.message || '无法下载 EAR 模板，请稍后重试。',
    })
  }
}

function getDepartmentActiveToolIds(departmentCode) {
  return activeToolIdsByDepartment.value[departmentCode] || []
}

function isToolActive(departmentCode, toolId) {
  return getDepartmentActiveToolIds(departmentCode).includes(toolId)
}

function setToolPendingState(departmentCode, toolId, pending) {
  const key = getToolKey(departmentCode, toolId)
  if (pending) {
    pendingToolKeys.value = {
      ...pendingToolKeys.value,
      [key]: true,
    }
    return
  }

  const nextState = { ...pendingToolKeys.value }
  delete nextState[key]
  pendingToolKeys.value = nextState
}

function isToolPending(departmentCode, toolId) {
  return Boolean(pendingToolKeys.value[getToolKey(departmentCode, toolId)])
}

function isToolBusy(departmentCode, toolId) {
  return isToolPending(departmentCode, toolId) || isToolActive(departmentCode, toolId)
}

function setDepartmentActiveTools(departmentCode, toolIds) {
  activeToolIdsByDepartment.value = {
    ...activeToolIdsByDepartment.value,
    [departmentCode]: [...toolIds],
  }
}

function addActiveTool(departmentCode, toolId) {
  const current = new Set(getDepartmentActiveToolIds(departmentCode))
  current.add(toolId)
  setDepartmentActiveTools(departmentCode, [...current])
}

function handleActiveToolsChange(payload) {
  if (!payload?.department) {
    return
  }

  setDepartmentActiveTools(payload.department, payload.toolIds || [])
}

function focusDepartmentFromGlobalTasks(departmentCode) {
  if (!departmentCode) {
    return
  }
  activeDepartmentCode.value = departmentCode
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

async function refreshExecutionViews() {
  await Promise.allSettled([
    logPanel.value?.refresh?.({ silent: true }),
    globalRunningBar.value?.refresh?.({ silent: true }),
  ])
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
      detail: '未能连接到后端服务，请确认 FastAPI 已启动且地址可访问。',
    }
  }
}

async function loadDepartmentConfig(department) {
  try {
    const response = await getDepartmentConfig(department)
    if (response?.success && response.config) {
      const networkPath = response.config.networkPath || ''
      departmentConfig.value = {
        networkPath
      }
      configPanelOpen.value = !sanitizePathInput(networkPath)
    } else {
      departmentConfig.value = {
        networkPath: ''
      }
      configPanelOpen.value = true
    }
  } catch (error) {
    console.error('Failed to load department config:', error)
  }
}

async function saveDepartmentConfiguration() {
  const dept = activeDepartmentCode.value
  savingDepartmentConfig.value = true
  try {
    const networkPath = sanitizePathInput(departmentConfig.value.networkPath)
    departmentConfig.value.networkPath = networkPath
    const response = await saveDepartmentConfig(dept, {
      networkPath
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
  } finally {
    savingDepartmentConfig.value = false
  }
}

async function testDeptNetworkPath(options = {}) {
  const { silentSuccess = false } = options
  const path = sanitizePathInput(departmentConfig.value.networkPath)
  if (!path) {
    networkPathTestResult.value = { success: false, message: '请先输入网络路径' }
    return false
  }
  departmentConfig.value.networkPath = path

  testingNetworkPath.value = true
  networkPathTestResult.value = null

  try {
    const response = await testNetworkPath(path)
    networkPathTestResult.value = {
      success: Boolean(response?.success),
      message: response?.message || response?.error || '测试完成'
    }
    if (response?.success && !silentSuccess) {
      pushToast({
        type: 'success',
        title: '连接成功',
        message: '网络路径可正常访问。',
      })
    }
    return Boolean(response?.success)
  } catch (error) {
    networkPathTestResult.value = {
      success: false,
      message: error.message || '网络请求失败'
    }
    return false
  } finally {
    testingNetworkPath.value = false
  }
}

async function ensureNetworkPathReadyForTool(departmentCode, toolId) {
  if (!toolRequiresNetworkPath(departmentCode, toolId)) {
    return true
  }

  const success = await testDeptNetworkPath({ silentSuccess: true })
  if (!success) {
    pushToast({
      type: 'error',
      title: '共享盘连接失败',
      message: networkPathTestResult.value?.message || '请先完成局域网路径测试并确保可读写。',
      duration: 5200,
    })
    return false
  }

  try {
    const response = await saveDepartmentConfig(departmentCode, {
      networkPath: departmentConfig.value.networkPath,
    })
    if (!response?.success) {
      throw new Error(response?.error || '局域网路径保存失败')
    }
  } catch (error) {
    pushToast({
      type: 'error',
      title: '共享盘路径保存失败',
      message: error.message || '无法保存当前局域网路径配置。',
      duration: 5200,
    })
    return false
  }
  return success
}

async function loadToolConfig(department, toolId) {
  try {
    const response = await getToolConfig(department, toolId)
    const cfg = response?.success && response.config ? response.config : {}
    configData.value = {
      ...createDefaultConfigData(),
      folderPath: cfg.folderPath || '',
      folderDisplay: cfg.folderDisplay || cfg.folderPath || '',
      excelPath: cfg.excelPath || cfg.listExcelPath || '',
      listExcelPath: cfg.listExcelPath || '',
      listExcelDisplay: cfg.listExcelDisplay || cfg.listExcelPath || cfg.excelPath || '',
      excelFilePath: cfg.excelFilePath || cfg.excelFolderPath || '',
      excelFileDisplay: cfg.excelFileDisplay || cfg.excelFilePath || cfg.excelFolderDisplay || cfg.excelFolderPath || '',
      excelFolderPath: cfg.excelFilePath || cfg.excelFolderPath || '',
      excelFolderDisplay: cfg.excelFileDisplay || cfg.excelFilePath || cfg.excelFolderDisplay || cfg.excelFolderPath || '',
      reportYear: cfg.reportYear || '',
      reportMonthGerman: cfg.reportMonthGerman || '',
      email: cfg.email || '',
      authCode: cfg.authCode || '',
      maxEmails: cfg.maxEmails || 50,
      subjectKeyword: cfg.subjectKeyword || '注销成功',
      selectedFolder: cfg.selectedFolder || '',
    }
    cacheToolConfig(department, toolId, configData.value)
  } catch (error) {
    console.error('Failed to load config:', error)
  }
}

async function preloadDepartmentToolConfigs(departmentCode) {
  const department = departments.find((item) => item.code === departmentCode)
  if (!department) {
    return
  }

  const configurableTools = department.tools.filter((tool) => tool.configurable)
  await Promise.allSettled(configurableTools.map(async (tool) => {
    const response = await getToolConfig(departmentCode, tool.id)
    const config = response?.success && response.config ? response.config : {}

    if (tool.id === 'invoice_recognizer') {
      cacheToolConfig(departmentCode, tool.id, normalizeInvoiceRecognizerConfig(config))
      return
    }

    if (tool.id === 'ear_declaration_data_fetcher') {
      cacheToolConfig(departmentCode, tool.id, normalizeEarDeclarationFetcherConfig(config))
      return
    }

    cacheToolConfig(departmentCode, tool.id, {
      ...createDefaultConfigData(),
      ...config,
    })
  }))
}

// Legacy support
async function loadInvoiceConfig() {
  await loadToolConfig(PREVIEW_DEPARTMENT, PREVIEW_TOOL_ID)
}

async function openConfigDialog(tool) {
  currentConfigTool.value = {
    department: activeDepartmentCode.value,
    toolId: tool.id,
  }
  configData.value = createDefaultConfigData()
  mailFolders.value = []
  mailFoldersError.value = ''
  configDialogOpen.value = true
  loadingToolConfig.value = true

  try {
    await loadToolConfig(activeDepartmentCode.value, tool.id)

    if (tool.id === 'citeo_email_extractor' && configData.value.email && configData.value.authCode) {
      await loadMailFolders()
    }
  } finally {
    loadingToolConfig.value = false
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
    const result = await listMailFolders({ email, authCode })
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
      mailFoldersError.value = result?.error || '无法获取文件夹列表，请检查邮箱账号、授权码和 IMAP 设置。'
    }
  } catch (error) {
    mailFolders.value = []
    mailFoldersError.value = '网络请求失败，请检查网络连接。'
  } finally {
    loadingFolders.value = false
  }
}

async function saveConfiguration() {
  if (loadingToolConfig.value) {
    return
  }

  const { department, toolId } = currentConfigTool.value
  const targetDept = department || PREVIEW_DEPARTMENT
  const targetTool = toolId || PREVIEW_TOOL_ID
  savingToolConfig.value = true

  try {
    let payload = { ...configData.value }

    if (targetTool === 'invoice_recognizer') {
      payload = normalizeInvoiceRecognizerConfig(configData.value)
    } else if (targetTool === 'ear_declaration_data_fetcher') {
      payload = normalizeEarDeclarationFetcherConfig(configData.value)
    }

    if (targetTool === 'invoice_recognizer') {
      validateInvoiceRecognizerManualPathsOrThrow(payload)
    } else if (targetTool === 'ear_declaration_data_fetcher') {
      validateEarDeclarationFetcherConfigOrThrow(payload)
    }

    const response = await saveConfig(targetDept, targetTool, payload)
    if (!response?.success) {
      throw new Error(response?.error || '保存失败')
    }

    configData.value = payload
    cacheToolConfig(targetDept, targetTool, payload)

    configDialogOpen.value = false
    pushToast({
      type: 'success',
      title: '配置已保存',
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
  } finally {
    savingToolConfig.value = false
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
      message: '当前仅对英德单据识别提供预览能力。',
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

function focusExecutionPanel() {
  const panel = document.querySelector('.aside-card')
  panel?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function handleToolPrimaryAction(tool) {
  const setupState = getToolSetupState(activeDepartmentCode.value, tool)

  if (setupState.primaryAction === 'open-path') {
    configPanelOpen.value = true
    return
  }

  if (setupState.primaryAction === 'open-config') {
    await openConfigDialog(tool)
    return
  }

  if (setupState.primaryAction === 'focus-log') {
    focusExecutionPanel()
    return
  }

  if (setupState.primaryAction === 'run') {
    await runDepartmentScript(tool)
  }
}

async function runDepartmentScript(tool) {
  if (tool.action !== 'run_script') {
    return
  }

  const departmentCode = activeDepartmentCode.value
  if (isToolBusy(departmentCode, tool.id)) {
    return
  }

  setToolPendingState(departmentCode, tool.id, true)

  try {
    let runtimeConfigOverride = null
    const networkReady = await ensureNetworkPathReadyForTool(departmentCode, tool.id)
    if (!networkReady) {
      return
    }

    if (tool.id === 'invoice_recognizer') {
      const cacheKey = getToolKey(departmentCode, tool.id)
      const cachedConfig = toolConfigCache.value[cacheKey]
      const configSource = cachedConfig || (await getToolConfig(departmentCode, tool.id))?.config || {}

      runtimeConfigOverride = {
        folderPath: configSource.folderPath || '',
        folderDisplay: configSource.folderPath || '',
        excelPath: configSource.excelPath || configSource.listExcelPath || '',
        listExcelPath: configSource.listExcelPath || configSource.excelPath || '',
        listExcelDisplay: configSource.listExcelPath || configSource.excelPath || '',
      }

      if (!runtimeConfigOverride.folderPath || !runtimeConfigOverride.listExcelPath) {
        pushToast({
          type: 'warning',
          title: '请先填写路径',
          message: '先填写共享盘中的单据文件夹和 Excel 清单路径，再运行识别。',
        })
        return
      }
    }

    const result = await runDepartmentTool(departmentCode, tool.id, runtimeConfigOverride)

    if (result?.success && ['queued', 'running'].includes(result?.status)) {
      addActiveTool(departmentCode, tool.id)
      globalRunningBar.value?.onTaskStarted({
        toolId: tool.id,
        logId: result.logId,
        status: result.status,
      })
      logPanel.value?.onTaskStarted({
        toolId: tool.id,
        logId: result.logId,
        status: result.status,
      })
      await refreshExecutionViews()
      pushToast({
        type: 'info',
        title: result.status === 'queued' ? '任务已入队' : '任务已启动',
        message: result.status === 'queued'
          ? `${tool.name} 正在排队，请查看右侧执行记录。`
          : `${tool.name} 正在后台运行，请查看右侧执行记录。`,
        duration: 3000,
      })
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
      message: error.message || '请确认 FastAPI 服务已启动，例如 uvicorn main:app --reload。',
      duration: 5200,
    })
  } finally {
    setToolPendingState(departmentCode, tool.id, false)
  }
}

watch(activeDepartmentCode, async (departmentCode) => {
  try {
    localStorage.setItem(STORAGE_KEY, departmentCode)
  } catch {
    // localStorage 不可用时静默处理
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
  await Promise.all([
    loadDepartmentConfig(activeDepartmentCode.value),
    preloadDepartmentToolConfigs(activeDepartmentCode.value),
  ])
})

// 监听部门切换并加载对应配置
watch(activeDepartmentCode, async (newDept) => {
  await Promise.all([
    loadDepartmentConfig(newDept),
    preloadDepartmentToolConfigs(newDept),
  ])
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
    <header class="page-header">
      <div class="page-copy">
        <UiBadge variant="secondary">部门工作台</UiBadge>
        <h1>先看清状态，再开始执行</h1>
        <p class="page-lead">
          把常用任务、目录配置和运行反馈放回同一条操作链里，减少使用者在页面上来回判断的成本。
        </p>
      </div>
      <UiCard class="hero-strip">
        <div class="hero-strip-copy">
          <div class="hero-strip-head">
            <p class="section-label">当前部门</p>
            <UiBadge :variant="activeDepartmentStatus.variant">{{ activeDepartmentStatus.label }}</UiBadge>
          </div>
          <h2>{{ activeDepartment.name }}</h2>
          <p>{{ activeDepartmentStatus.description }}</p>
        </div>
        <div class="hero-strip-stats">
          <div v-for="item in activeDepartmentOverview" :key="item.label" class="hero-stat">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
            <small>{{ item.hint }}</small>
          </div>
        </div>
      </UiCard>
    </header>

    <UiCard class="switcher-card">
      <div class="tabs-head">
        <div>
          <p class="section-label">部门切换</p>
          <h2>选择你现在要处理的工作区</h2>
          <p class="switcher-copy">先确认部门，再看下方任务是否已经就绪。</p>
        </div>
        <div class="switcher-status">
          <UiBadge :variant="statusBadgeVariant">{{ connectionStatus.label }}</UiBadge>
          <small>{{ connectionStatus.detail }}</small>
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

    <GlobalRunningTasksBar
      ref="globalRunningBar"
      :limit="50"
      :display-limit="4"
      @focus-department="focusDepartmentFromGlobalTasks"
    />

    <section class="content-grid">
      <UiCard class="department-card">
        <div class="department-header department-header--stacked">
          <div class="department-copy">
            <div class="department-badges">
              <UiBadge>{{ activeDepartment.code }}</UiBadge>
              <UiBadge variant="secondary">{{ activeToolCount }} 个任务</UiBadge>
              <UiBadge :variant="activeDepartmentStatus.variant">{{ activeDepartmentStatus.label }}</UiBadge>
            </div>
            <h2>{{ activeDepartment.name }}</h2>
            <p>{{ activeDepartmentStatus.description }}</p>
          </div>
          <div class="department-header-actions">
            <UiButton variant="outline" @click="configPanelOpen = !configPanelOpen">
              {{ configPanelToggleLabel }}
            </UiButton>
            <UiButton
              variant="outline"
              :loading="testingNetworkPath"
              :disabled="savingDepartmentConfig"
              @click="testDeptNetworkPath"
            >
              测试目录
            </UiButton>
          </div>
        </div>

        <div class="overview-grid">
          <div v-for="item in activeDepartmentOverview" :key="item.label" class="overview-card">
            <span class="section-label">{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
            <small>{{ item.hint }}</small>
          </div>
        </div>

        <div class="workspace-toolbar">
          <div class="workspace-toolbar-copy">
            <p class="section-label">部门目录</p>
            <strong>{{ normalizedDepartmentNetworkPath || '尚未配置共享目录' }}</strong>
            <small>
              {{ activeDepartmentNeedsNetworkPath ? '当前部门有任务依赖共享目录，建议先验证可读写。' : '当前部门没有强依赖共享目录的任务。' }}
            </small>
          </div>
          <div class="workspace-toolbar-actions">
            <UiBadge :variant="networkPathBadgeVariant">{{ networkPathStatusLabel }}</UiBadge>
            <UiButton :loading="savingDepartmentConfig" :disabled="testingNetworkPath" @click="saveDepartmentConfiguration">
              保存目录
            </UiButton>
          </div>
        </div>

        <div v-if="configPanelOpen" class="department-config-section">
          <div class="department-config-head minimal">
            <div>
              <p class="section-label">配置区</p>
              <h3>部门共享目录</h3>
              <p class="department-config-copy">
                只在需要时展开编辑，避免首页长期被配置表单占满。
              </p>
            </div>
          </div>
          <div class="config-row">
            <div class="config-field">
              <UiLabel for="network-path">部门局域网目录</UiLabel>
              <UiInput
                id="network-path"
                v-model="departmentConfig.networkPath"
                placeholder="Windows 示例：\\\\服务器\\共享文件夹\\BUE2 或 D:\\工作目录\\BUE2"
              />
            </div>
            <div class="config-actions">
              <UiButton
                variant="outline"
                :loading="testingNetworkPath"
                :disabled="savingDepartmentConfig"
                @click="testDeptNetworkPath"
              >
                测试连接
              </UiButton>
              <UiButton :loading="savingDepartmentConfig" :disabled="testingNetworkPath" @click="saveDepartmentConfiguration">
                保存配置
              </UiButton>
            </div>
          </div>
          <div class="config-note-row">
            <div class="test-result config-tip">
              这里填写局域网数据存储地址，例如 `\\192.168.76.93\厦门部门\BUE2`。
            </div>
            <div
              v-if="networkPathTestResult"
              class="test-result"
              :class="{ success: networkPathTestResult.success, error: !networkPathTestResult.success }"
            >
              {{ networkPathTestResult.message }}
            </div>
          </div>
        </div>

        <div class="tools-section-head">
          <div>
            <p class="section-label">任务入口</p>
            <h3>按“能否立刻执行”来组织工具</h3>
            <p>每张卡片都直接告诉你当前缺什么、下一步该点哪里，不再让使用者自己推断。</p>
          </div>
        </div>

        <div class="tool-grid">
          <UiCard
            v-for="tool in activeToolCards"
            :key="tool.id"
            class="tool-card"
            :tone="tool.setupState.key === 'ready' ? 'default' : 'muted'"
          >
            <div class="tool-card-head">
              <div class="tool-card-headline">
                <div class="tool-card-badges">
                  <UiBadge variant="secondary">{{ tool.tag }}</UiBadge>
                  <UiBadge :variant="tool.setupState.variant">{{ tool.setupState.label }}</UiBadge>
                </div>
                <h3>{{ tool.name }}</h3>
              </div>
            </div>
            <div class="tool-card-body">
              <p>{{ tool.description }}</p>
              <p class="tool-card-state-copy">{{ tool.setupState.description }}</p>
              <div class="tool-card-meta">
                <UiBadge v-if="tool.configurable" variant="outline">支持配置</UiBadge>
                <UiBadge
                  v-if="toolRequiresNetworkPath(activeDepartmentCode, tool.id)"
                  variant="warning"
                >
                  依赖共享目录
                </UiBadge>
                <UiBadge v-if="tool.previewable" variant="outline">支持预览</UiBadge>
              </div>
            </div>
            <div class="tool-card-foot">
              <div class="tool-card-actions">
                <UiButton
                  v-if="tool.configurable"
                  variant="outline"
                  :disabled="isToolPending(activeDepartmentCode, tool.id)"
                  @click="openConfigDialog(tool)"
                >
                  配置
                </UiButton>
                <UiButton
                  v-if="tool.previewable"
                  variant="outline"
                  @mouseenter="warmToolPreview(tool)"
                  @focus="warmToolPreview(tool)"
                  @click="openToolPreview(tool)"
                >
                  预览
                </UiButton>
              </div>
              <UiButton
                :variant="tool.setupState.key === 'ready' ? 'default' : 'outline'"
                :loading="tool.setupState.primaryAction === 'run' && isToolBusy(activeDepartmentCode, tool.id)"
                :disabled="tool.setupState.primaryDisabled || isToolPending(activeDepartmentCode, tool.id)"
                @click="handleToolPrimaryAction(tool)"
              >
                {{ tool.setupState.primaryLabel }}
              </UiButton>
            </div>
          </UiCard>
        </div>
      </UiCard>

      <aside class="aside-card">
        <ExecutionLogPanel
          ref="logPanel"
          :department="activeDepartment.code"
          :limit="12"
          @active-tools-change="handleActiveToolsChange"
          @execution-mutated="globalRunningBar?.refresh?.({ silent: true })"
        />
      </aside>
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
      :title="activeConfigDialogTitle"
      :description="activeConfigDialogDescription"
    >
      <div v-if="loadingToolConfig" class="config-loading-state">
        <UiBadge variant="secondary">加载中</UiBadge>
        <p>正在同步当前工具配置，请稍候。</p>
      </div>

      <!-- 顾问部单据识别配置 -->
      <div v-else-if="currentConfigTool.toolId === 'ear_declaration_data_fetcher'" class="config-form">
        <div class="form-field">
          <UiLabel for="ear-excel-file-path">申报数据 Excel 文件</UiLabel>
          <div class="folder-select-header">
            <UiLabel for="ear-excel-file-path">申报数据 Excel 文件</UiLabel>
            <UiButton variant="outline" @click="downloadEarTemplate">
              下载模板
            </UiButton>
          </div>
          <UiInput
            id="ear-excel-file-path"
            :model-value="configData.excelFilePath || configData.excelFileDisplay || configData.excelFolderPath || configData.excelFolderDisplay"
            @update:model-value="updateEarExcelFilePath"
            placeholder="请填写申报数据 Excel 的绝对路径"
          />
          <small class="field-hint">当前会校验该 Excel 文件是否已填写；运行时只读取这一个表，不再扫描整个文件夹。</small>
        </div>

        <div class="form-field">
          <UiLabel for="ear-report-year">检测年份</UiLabel>
          <UiInput
            id="ear-report-year"
            :model-value="configData.reportYear"
            @update:model-value="value => { configData.reportYear = String(value || '').trim() }"
            placeholder="例如 2026"
          />
        </div>

        <div class="form-field">
          <UiLabel for="ear-report-month-german">检测月份（德语）</UiLabel>
          <UiInput
            id="ear-report-month-german"
            :model-value="configData.reportMonthGerman"
            @update:model-value="value => { configData.reportMonthGerman = String(value || '').trim() }"
            placeholder="例如 März"
          />
        </div>

        <div class="form-field">
          <small class="field-hint">表头需包含：授权代表\nbevollmächtigter Vertreter、WEEE号\nWEEE-Nummer、中文名\nFirmenname auf Chinesisch、英文名\nFirmenname auf Englisch、类别\nKategorie、德语类目、账号、密码、*月申报数据、官网上抓取的数据（*月）。年份和德语月份从配置项读取，不再从 Excel 表中读取。</small>
          <small class="field-hint">可先点击“下载模板”获取 Excel 示例。</small>
        </div>
      </div>

      <div v-else-if="currentConfigTool.toolId !== 'citeo_email_extractor'" class="config-form">
        <div class="form-field">
          <UiLabel for="folder-path">递延税单据总文件夹</UiLabel>
          <UiInput
            id="folder-path"
            :model-value="configData.folderPath || configData.folderDisplay"
            @update:model-value="updateInvoiceFolderPath"
            placeholder="请填写部署电脑可访问的真实绝对路径，例如 \\\\服务器\\共享\\顾问部\\英德单据"
          />
          <small class="field-hint">仅支持手动填写真实路径。保存或运行时会校验目录是否可读可写，且必须在当前部门共享根目录下；像 `C:\\Users\\...` 这类用户本机路径会被拦截。</small>
        </div>

        <div class="form-field">
          <UiLabel for="list-excel-path">Excel 清单文件</UiLabel>
          <UiInput
            id="list-excel-path"
            :model-value="configData.listExcelPath || configData.listExcelDisplay"
            @update:model-value="updateInvoiceExcelPath"
            placeholder="请填写部署电脑可访问的 .xlsx 真实绝对路径"
          />
          <small class="field-hint">保存或运行时会校验 Excel 文件是否可读，并同时确认该路径属于当前部门共享根目录。</small>
        </div>
      </div>

      <!-- BUE2 邮件提取配置 -->
      <div v-else class="config-form">
        <div class="form-field">
          <UiLabel for="email">163 邮箱账号</UiLabel>
          <UiInput
            id="email"
            v-model="configData.email"
            type="email"
            placeholder="your_email@163.com"
            disabled
          />
        </div>

        <div class="form-field">
          <small class="field-hint">提示：点击“加载文件夹”，选择存放注销邮件的文件夹，填写获取邮件数量后保存配置即可运行。邮箱和授权码已预配置，如需修改请联系管理员。</small>
        </div>

        <div class="form-field">
          <div class="folder-select-header">
            <UiLabel for="mail-folder">选择邮件文件夹（存放注销邮件的文件夹）</UiLabel>
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
        <UiButton
          variant="outline"
          :disabled="savingToolConfig"
          @click="configDialogOpen = false"
        >
          取消
        </UiButton>
        <UiButton
          :loading="savingToolConfig"
          :disabled="loadingToolConfig || savingToolConfig"
          @click="saveConfiguration"
        >
          保存配置
        </UiButton>
      </template>
    </UiDialog>

    <UiToastStack class="page-toast-stack" :toasts="toasts" @dismiss="dismissToast" />
  </div>
</template>

<style scoped>
.page-shell {
  position: relative;
  min-height: 100vh;
  padding: 1.5rem;
}

.page-shell > *:not(.page-toast-stack) {
  position: relative;
  z-index: 1;
}

.hero-strip {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: 1rem;
  margin-top: 0.5rem;
}

.hero-strip-copy,
.hero-strip-stats {
  display: grid;
  gap: 0.75rem;
}

.hero-strip-head {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  align-items: center;
  flex-wrap: wrap;
}

.hero-strip-copy h2 {
  font-size: clamp(1.5rem, 3vw, 2.2rem);
  line-height: 1.05;
  letter-spacing: -0.04em;
}

.hero-strip-copy p:last-child,
.switcher-copy,
.switcher-status small,
.department-config-copy,
.workspace-toolbar-copy small {
  color: var(--muted-foreground);
  line-height: 1.6;
}

.hero-strip-stats,
.overview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.hero-stat,
.overview-card {
  display: grid;
  gap: 0.4rem;
  padding: 1rem 1.05rem;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--card-muted);
}

.hero-stat strong,
.overview-card strong {
  font-size: 1.2rem;
  line-height: 1.15;
  letter-spacing: -0.03em;
}

.hero-stat small,
.overview-card small {
  color: var(--muted-foreground);
  line-height: 1.55;
}

.switcher-card {
  margin-top: 1.25rem;
}

.switcher-status {
  display: grid;
  gap: 0.45rem;
  justify-items: end;
  max-width: 24rem;
}

.department-header--stacked {
  justify-content: space-between;
  align-items: flex-start;
}

.department-header-actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.overview-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.department-config-section {
  margin: 0.25rem 0 0;
  padding: 1rem;
  background: var(--card-muted);
  border-radius: 16px;
  border: 1px solid var(--border);
}

.department-config-head {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.department-config-head h3 {
  margin: 0.5rem 0 0;
  font-size: 1.1rem;
  line-height: 1.2;
  letter-spacing: -0.02em;
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

.config-note-row {
  display: grid;
  gap: 0.75rem;
}

.test-result {
  margin-top: 0.75rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  font-size: 0.875rem;
  border: 1px solid transparent;
}

.config-tip {
  color: var(--muted-foreground);
  background: var(--card);
  border-color: var(--border);
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

.config-loading-state {
  display: grid;
  gap: 0.75rem;
  padding: 0.25rem 0 0.5rem;
}

.config-loading-state p {
  margin: 0;
  color: var(--muted-foreground);
  line-height: 1.6;
}

.form-field > .ui-label:has(+ .folder-select-header) {
  display: none;
}

.folder-select-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.tool-card {
  gap: 0.9rem;
}

.tool-card-headline,
.tool-card-badges {
  display: grid;
  gap: 0.55rem;
}

.tool-card-headline h3 {
  font-size: 1.08rem;
  line-height: 1.2;
  letter-spacing: -0.03em;
}

.tool-card-state-copy {
  color: var(--foreground);
  font-size: 0.88rem;
  line-height: 1.55;
}

@media (max-width: 900px) {
  .hero-strip,
  .overview-grid,
  .department-config-head,
  .config-row,
  .folder-select-header,
  .department-header--stacked {
    grid-template-columns: 1fr;
    flex-direction: column;
    align-items: stretch;
  }

  .hero-strip-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .switcher-status {
    justify-items: start;
    max-width: none;
  }

  .config-actions {
    width: 100%;
  }

  .config-actions > * {
    flex: 1 1 0;
  }
}

@media (max-width: 720px) {
  .hero-strip-stats,
  .overview-grid {
    grid-template-columns: 1fr;
  }

  .department-header-actions,
  .workspace-toolbar-actions {
    width: 100%;
  }

  .department-header-actions > *,
  .workspace-toolbar-actions > * {
    flex: 1 1 0;
  }
}
</style>
