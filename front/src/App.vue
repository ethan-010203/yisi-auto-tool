<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getData, getToolConfig, getToolPreview, runDepartmentTool, saveConfig, getDepartmentConfig, saveDepartmentConfig, testNetworkPath } from './api/index'
import ExecutionLogPanel from './components/ExecutionLogPanel.vue'
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
const toolConfigCache = ref({})
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
const NETWORK_REQUIRED_TOOL_KEYS = new Set([])

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

function getDepartmentActiveToolIds(departmentCode) {
  return activeToolIdsByDepartment.value[departmentCode] || []
}

function isToolActive(departmentCode, toolId) {
  return getDepartmentActiveToolIds(departmentCode).includes(toolId)
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
      detail: '未能连接到后端服务，请确认 FastAPI 已启动且地址可访问。',
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
  const { department, toolId } = currentConfigTool.value
  const targetDept = department || PREVIEW_DEPARTMENT
  const targetTool = toolId || PREVIEW_TOOL_ID

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

async function runDepartmentScript(tool) {
  if (tool.action !== 'run_script') {
    return
  }

  const departmentCode = activeDepartmentCode.value

  try {
    let runtimeConfigOverride = null
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
      pushToast({
        type: 'info',
        title: result.status === 'queued' ? '任务已入队' : '任务已启动',
        message: result.status === 'queued'
          ? `${tool.name} 正在排队，请查看右侧执行记录。`
          : `${tool.name} 正在后台运行，请查看右侧执行记录。`,
        duration: 3000,
      })
      logPanel.value?.onTaskStarted(tool.id)
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
  await loadDepartmentConfig(activeDepartmentCode.value)
})

// 监听部门切换并加载对应配置
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
    <header class="page-header">
      <div class="page-copy">
        <UiBadge variant="secondary">部门工作台</UiBadge>
        <h1>部门工具工作台</h1>
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
          <p class="section-label">部门列表</p>
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
            </div>
            <h2>{{ activeDepartment.name }}</h2>
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
                placeholder="Windows 示例：\\\\服务器\\共享文件夹\\BUE2 或 D:\\工作目录\\BUE2"
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
          <div class="test-result">
            这里填写局域网数据存储地址，例如 `\\192.168.76.93\厦门部门\BUE2`。
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
              <UiBadge v-if="tool.previewable" variant="outline">支持预览</UiBadge>
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
                  :loading="isToolActive(activeDepartmentCode, tool.id)"
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
                  :loading="isToolActive(activeDepartmentCode, tool.id)"
                  @click="runDepartmentScript(tool)"
                >
                  {{ isToolActive(activeDepartmentCode, tool.id) ? '运行中' : '运行' }}
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
          @active-tools-change="handleActiveToolsChange"
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
      :title="activeConfigDialogTitle"
      :description="activeConfigDialogDescription"
    >
      <!-- 顾问部单据识别配置 -->
      <div v-if="currentConfigTool.toolId === 'ear_declaration_data_fetcher'" class="config-form">
        <div class="form-field">
          <UiLabel for="ear-excel-file-path">申报数据 Excel 文件</UiLabel>
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
          <small class="field-hint">表头需包含：授权代表\nbevollmächtigter Vertreter、WEEE号\nWEEE-Nummer、中文名\nFirmenname auf Chinesisch、英文名\nFirmenname auf Englisch、类别\nKategorie、德语类目、账号、密码、3月申报数据、官网上抓取的数据（3月）。年份和德语月份从配置项读取，不再从 Excel 表中读取。</small>
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
        <UiButton variant="outline" @click="configDialogOpen = false">取消</UiButton>
        <UiButton @click="saveConfiguration">保存配置</UiButton>
      </template>
    </UiDialog>

    <UiToastStack class="page-toast-stack" :toasts="toasts" @dismiss="dismissToast" />
  </div>
</template>

<style scoped>
/* Page shell */
.page-shell {
  position: relative;
  min-height: 100vh;
  padding: 1.5rem;
}

.page-shell > *:not(.page-toast-stack) {
  position: relative;
  z-index: 1;
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

</style>
