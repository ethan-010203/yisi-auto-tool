<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getData, getDepartments, getToolConfig, getToolPreview, runDepartmentTool, testNetworkPath } from './api/index'
import ConfigDialog from './components/ConfigDialog.vue'
import DepartmentSidebar from './components/DepartmentSidebar.vue'
import ExecutionLogPanel from './components/ExecutionLogPanel.vue'
import GlobalRunningTasksBar from './components/GlobalRunningTasksBar.vue'
import NetworkSettingsPanel from './components/NetworkSettingsPanel.vue'
import ToolGrid from './components/ToolGrid.vue'
import ToolPreviewDialog from './components/preview/ToolPreviewDialog.vue'
import UiButton from './components/ui/UiButton.vue'
import UiCard from './components/ui/UiCard.vue'
import UiPageHeader from './components/ui/UiPageHeader.vue'
import UiToastStack from './components/ui/UiToastStack.vue'
import { useExecutionEvents } from './composables/useExecutionEvents'
import {
  normalizeInvoiceRecognizerConfig,
  sanitizePathInput,
  useToolConfig,
} from './composables/useToolConfig'
import { departmentNetworkPaths as fallbackDepartmentNetworkPaths, departments as fallbackDepartments } from './data/departments'

const PREVIEW_TOOL_ID = 'invoice_recognizer'
const PREVIEW_DEPARTMENT = 'CONSULT'

const STORAGE_KEY = 'yisi-auto-tool:department'
const WORKSPACE_VIEW_STORAGE_KEY = 'yisi-auto-tool:workspace-view'

const getSavedDepartment = () => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && fallbackDepartments.some(d => d.code === saved)) {
      return saved
    }
  } catch {
    // localStorage 不可用时回退到默认部门
  }
  return fallbackDepartments[0].code
}

const saveDepartment = (departmentCode) => {
  try {
    localStorage.setItem(STORAGE_KEY, departmentCode)
  } catch {
    // localStorage 不可用时静默处理
  }
}

const saveWorkspaceView = (workspaceView) => {
  try {
    localStorage.setItem(WORKSPACE_VIEW_STORAGE_KEY, workspaceView)
  } catch {
    // localStorage 不可用时静默处理
  }
}

const getSavedWorkspaceView = () => {
  try {
    const saved = localStorage.getItem(WORKSPACE_VIEW_STORAGE_KEY)
    if (saved === 'dashboard' || saved === 'department') {
      return saved
    }
  } catch {
    return 'dashboard'
  }
  return 'dashboard'
}

const activeDepartmentCode = ref(getSavedDepartment())
const activeWorkspaceView = ref(getSavedWorkspaceView())
const activeDashboardTab = ref('overview')
const departments = ref([...fallbackDepartments])
const previewDialogOpen = ref(false)
const previewLoading = ref(false)
const previewData = ref(null)
const previewTargetKey = ref('')
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
const departmentNetworkPaths = ref({ ...fallbackDepartmentNetworkPaths })
const departmentConfigs = ref({ ...fallbackDepartmentNetworkPaths })
const testingNetworkPath = ref(false)
const testingAllNetworkPaths = ref(false)
const testingNetworkDepartment = ref('')
const networkPathTestResult = ref(null)
const previewCache = new Map()
let previewAbortController = null
const toastTimers = new Map()

function getToolKey(departmentCode, toolId) {
  return `${departmentCode}:${toolId}`
}

const {
  getDepartmentActiveToolIds,
  isToolPending,
  setToolPendingState,
  isToolBusy,
  addActiveTool,
  handleActiveToolsChange,
  refreshExecutionViews,
  notifyTaskStarted,
  refreshGlobalRunningBar,
} = useExecutionEvents({
  getToolKey,
  logPanel,
  globalRunningBar,
})

const {
  configDialogOpen,
  toolConfigCache,
  configData,
  currentConfigTool,
  mailFolders,
  loadingFolders,
  mailFoldersError,
  loadingToolConfig,
  savingToolConfig,
  folderOptions,
  activeConfigDialogTitle,
  activeConfigDialogDescription,
  hasSavedToolConfig,
  updateInvoiceFolderPath,
  updateInvoiceExcelPath,
  updateEarExcelFilePath,
  updateConfigField,
  downloadEarTemplate,
  loadToolConfig,
  preloadDepartmentToolConfigs,
  openConfigDialog,
  loadMailFolders,
  saveConfiguration,
} = useToolConfig({
  departments,
  activeDepartmentCode,
  getToolKey,
  pushToast,
  async onConfigSaved({ department, toolId }) {
    previewCache.delete(getToolKey(department, toolId))
    if (previewDialogOpen.value && previewTargetKey.value === getToolKey(department, toolId)) {
      await openToolPreview(findPreviewTool(), { force: true })
    }
  },
})

const activeDepartment = computed(() => {
  return departments.value.find((department) => department.code === activeDepartmentCode.value) ?? departments.value[0] ?? fallbackDepartments[0]
})

const totalTools = computed(() => {
  return departments.value.reduce((count, department) => count + department.tools.length, 0)
})

const activeToolCount = computed(() => {
  return activeDepartment.value.tools.length
})

const activeRunningToolCount = computed(() => {
  return getDepartmentActiveToolIds(activeDepartmentCode.value).length
})

const normalizedDepartmentNetworkPath = computed(() => getDepartmentNetworkPath(activeDepartmentCode.value))

const networkConfigRows = computed(() => {
  return departments.value.map((department) => ({
    ...department,
    networkPath: getDepartmentNetworkPath(department.code),
  }))
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
      primaryLabel: '运行中',
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

const dashboardOverview = computed(() => {
  return [
    {
      label: '部门数量',
      value: String(departments.value.length),
      hint: '左侧可切换工作区',
    },
    {
      label: '工具数量',
      value: String(totalTools.value),
      hint: '覆盖所有部门',
    },
    {
      label: '服务状态',
      value: connectionStatus.value.label,
      hint: connectionStatus.value.detail,
    },
    {
      label: '最近同步',
      value: lastUpdated.value,
      hint: '来自后端状态',
    },
  ]
})

const activeToolCards = computed(() => {
  return activeDepartment.value.tools.map((tool) => ({
    ...tool,
    setupState: getToolSetupState(activeDepartmentCode.value, tool),
  }))
})

function toolRequiresNetworkPath(departmentCode, toolId) {
  return Boolean(
    departments.value
      .find((department) => department.code === departmentCode)
      ?.tools.find((tool) => tool.id === toolId)
      ?.requiresNetworkPath
  )
}

function getDepartmentNetworkPath(departmentCode) {
  return sanitizePathInput(departmentConfigs.value[departmentCode] || departmentNetworkPaths.value[departmentCode] || '')
}

function showDashboard() {
  activeWorkspaceView.value = 'dashboard'
  saveWorkspaceView('dashboard')
  activeDashboardTab.value = 'overview'
}

function showNetworkConfig() {
  activeWorkspaceView.value = 'dashboard'
  saveWorkspaceView('dashboard')
  activeDashboardTab.value = 'network'
}

function selectDepartment(departmentCode) {
  activeDepartmentCode.value = departmentCode
  activeWorkspaceView.value = 'department'
  saveDepartment(departmentCode)
  saveWorkspaceView('department')
}

function focusDepartmentFromGlobalTasks(departmentCode) {
  if (!departmentCode) {
    return
  }
  selectDepartment(departmentCode)
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

async function loadDepartmentMetadata() {
  try {
    const response = await getDepartments()
    if (!response?.success || !Array.isArray(response.departments) || response.departments.length === 0) {
      return
    }

    departments.value = response.departments
    departmentNetworkPaths.value = {
      ...fallbackDepartmentNetworkPaths,
      ...(response.departmentNetworkPaths || Object.fromEntries(
        response.departments.map((department) => [department.code, department.networkPath || ''])
      )),
    }
    departmentConfigs.value = {
      ...departmentNetworkPaths.value,
    }

    if (!departments.value.some((department) => department.code === activeDepartmentCode.value)) {
      activeDepartmentCode.value = departments.value[0].code
    }
  } catch (error) {
    console.warn('Department metadata fallback in use:', error)
  }
}

async function testDeptNetworkPath(options = {}) {
  const { silentSuccess = false, departmentCode = activeDepartmentCode.value } = options
  const path = getDepartmentNetworkPath(departmentCode)
  if (!path) {
    networkPathTestResult.value = { success: false, message: '未配置网络路径', department: departmentCode }
    return false
  }

  testingNetworkPath.value = true
  testingNetworkDepartment.value = departmentCode
  networkPathTestResult.value = null

  try {
    const response = await testNetworkPath(path)
    const success = Boolean(response?.success)
    networkPathTestResult.value = {
      success,
      message: success ? '网络路径连接正常' : (response?.error || '网络路径连接失败'),
      department: departmentCode,
    }
    if (success && !silentSuccess) {
      pushToast({
        type: 'success',
        title: '连接成功',
        message: `${departmentCode} 网络路径连接正常。`,
      })
    }
    if (!success && !silentSuccess) {
      pushToast({
        type: 'error',
        title: '连接失败',
        message: `${departmentCode}：${networkPathTestResult.value.message}`,
      })
    }
    return success
  } catch (error) {
    networkPathTestResult.value = {
      success: false,
      message: error.message || '网络请求失败',
      department: departmentCode,
    }
    if (!silentSuccess) {
      pushToast({
        type: 'error',
        title: '连接失败',
        message: `${departmentCode}：${networkPathTestResult.value.message}`,
      })
    }
    return false
  } finally {
    testingNetworkPath.value = false
    testingNetworkDepartment.value = ''
  }
}

async function testAllNetworkPaths() {
  if (testingAllNetworkPaths.value || testingNetworkPath.value) {
    return
  }

  testingAllNetworkPaths.value = true
  const results = []
  try {
    for (const item of networkConfigRows.value) {
      const success = await testDeptNetworkPath({ departmentCode: item.code, silentSuccess: true })
      results.push({ ...item, success, message: networkPathTestResult.value?.message || '' })
    }

    const failed = results.filter((item) => !item.success)
    networkPathTestResult.value = {
      success: failed.length === 0,
      department: '全部门',
      message: failed.length === 0
        ? '全部部门局域网连接正常'
        : `${failed.length} 个部门连接失败：${failed.map((item) => item.name).join('、')}`,
    }

    pushToast({
      type: failed.length === 0 ? 'success' : 'error',
      title: failed.length === 0 ? '全部连接成功' : '部分连接失败',
      message: networkPathTestResult.value.message,
      duration: 5600,
    })
  } finally {
    testingAllNetworkPaths.value = false
    testingNetworkPath.value = false
    testingNetworkDepartment.value = ''
  }
}

async function ensureNetworkPathReadyForTool(departmentCode, toolId) {
  if (!toolRequiresNetworkPath(departmentCode, toolId)) {
    return true
  }

  const success = await testDeptNetworkPath({ silentSuccess: true, departmentCode })
  if (!success) {
    pushToast({
      type: 'error',
      title: '\u5171\u4eab\u76d8\u8fde\u63a5\u5931\u8d25',
      message: networkPathTestResult.value?.message || '\u8bf7\u786e\u8ba4\u5c40\u57df\u7f51\u914d\u7f6e\u9875\u4e2d\u7684\u56fa\u5b9a\u8def\u5f84\u53ef\u8bfb\u5199\u3002',
      duration: 5200,
    })
    return false
  }

  return true
}

async function loadInvoiceConfig() {
  await loadToolConfig(PREVIEW_DEPARTMENT, PREVIEW_TOOL_ID)
}

function findPreviewTool() {
  return departments.value
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
    pushToast({
      type: 'info',
      title: '\u5c40\u57df\u7f51\u8def\u5f84\u5df2\u56fa\u5b9a',
      message: '\u8bf7\u5728\u4eea\u8868\u76d8\u9875\u9762\u5185\u5207\u6362\u5230\u201c\u5c40\u57df\u7f51\u914d\u7f6e\u201d\u5b50 tab \u67e5\u770b\u6216\u6d4b\u8bd5\u3002',
    })
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

      runtimeConfigOverride = normalizeInvoiceRecognizerConfig(configSource)

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
      notifyTaskStarted({
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
  saveDepartment(departmentCode)
  if (departmentCode === PREVIEW_DEPARTMENT) {
    const tool = findPreviewTool()
    await warmToolPreview(tool)
  }
})

watch(activeWorkspaceView, (workspaceView) => {
  saveWorkspaceView(workspaceView)
})

watch(previewDialogOpen, (open) => {
  if (!open) {
    clearPreviewRequest()
    previewLoading.value = false
  }
})

onMounted(async () => {
  await Promise.all([loadConnectionStatus(), loadDepartmentMetadata(), loadInvoiceConfig()])
  await warmToolPreview(findPreviewTool())
  await Promise.all([
    preloadDepartmentToolConfigs(activeDepartmentCode.value),
  ])
})

// 监听部门切换并加载对应配置
watch(activeDepartmentCode, async (newDept) => {
  await Promise.all([
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
    <div class="workspace-shell">
      <DepartmentSidebar
        :departments="departments"
        :active-workspace-view="activeWorkspaceView"
        :active-department-code="activeDepartmentCode"
        :active-department="activeDepartment"
        :active-tool-count="activeToolCount"
        :connection-status="connectionStatus"
        :status-badge-variant="statusBadgeVariant"
        @show-dashboard="showDashboard"
        @select-department="selectDepartment"
      />

      <main class="workspace-main">
        <template v-if="activeWorkspaceView === 'dashboard'">
          <UiPageHeader
            eyebrow="全局仪表盘"
            title="先看全局，再进部门"
            lead="把所有部门的运行任务和基础配置集中放在这里，需要处理具体任务时再进入对应部门。"
            hero-label="总览"
            hero-title="仪表盘"
            hero-description="这里集中查看全局排队、运行、跨部门任务状态和固定局域网配置。"
            :status-label="connectionStatus.label"
            :status-variant="statusBadgeVariant"
            :stats="dashboardOverview"
          />

          <div class="dashboard-subtabs" role="tablist" aria-label="仪表盘子页">
            <UiButton :variant="activeDashboardTab === 'overview' ? 'default' : 'outline'" @click="showDashboard">
              运行总览
            </UiButton>
            <UiButton :variant="activeDashboardTab === 'network' ? 'default' : 'outline'" @click="showNetworkConfig">
              局域网配置
            </UiButton>
          </div>

          <div class="dashboard-tab-panel app-stable-content">
            <template v-if="activeDashboardTab === 'overview'">
              <GlobalRunningTasksBar
              ref="globalRunningBar"
              :limit="50"
              :display-limit="8"
              @active-tools-change="handleActiveToolsChange"
              @focus-department="focusDepartmentFromGlobalTasks"
              />
            </template>

            <NetworkSettingsPanel
              v-else
              :network-config-rows="networkConfigRows"
              :testing-all-network-paths="testingAllNetworkPaths"
              :testing-network-path="testingNetworkPath"
              :testing-network-department="testingNetworkDepartment"
              :network-path-test-result="networkPathTestResult"
              @test-all="testAllNetworkPaths"
              @test-department="departmentCode => testDeptNetworkPath({ departmentCode })"
            />
          </div>
        </template>

        <template v-else>
    <UiPageHeader
      eyebrow="部门工作台"
      title="先看清状态，再开始执行"
      lead="把常用任务、目录配置和运行反馈放回同一条操作链里，减少使用者在页面上来回判断的成本。"
      hero-label="当前部门"
      :hero-title="activeDepartment.name"
      network-label="固定共享目录"
      :network-value="normalizedDepartmentNetworkPath"
      :status-label="activeDepartmentStatus.label"
      :status-variant="activeDepartmentStatus.variant"
      :stats="activeDepartmentOverview"
    />

    <section class="content-grid app-stable-content">
      <UiCard class="department-card">
        <ToolGrid
          :tools="activeToolCards"
          :active-department-code="activeDepartmentCode"
          :tool-requires-network-path="toolRequiresNetworkPath"
          :is-tool-pending="isToolPending"
          :is-tool-busy="isToolBusy"
          @configure="openConfigDialog"
          @preview-warm="warmToolPreview"
          @preview="openToolPreview"
          @primary-action="handleToolPrimaryAction"
        />
      </UiCard>

      <aside class="aside-card">
        <ExecutionLogPanel
          ref="logPanel"
          :department="activeDepartment.code"
          :limit="12"
          @active-tools-change="handleActiveToolsChange"
          @execution-mutated="refreshGlobalRunningBar({ silent: true })"
        />
      </aside>
    </section>
        </template>
      </main>
    </div>

    <ToolPreviewDialog
      v-model:open="previewDialogOpen"
      :loading="previewLoading"
      :preview="previewData"
      @refresh="refreshPreview"
    />

    <ConfigDialog
      v-model:open="configDialogOpen"
      :title="activeConfigDialogTitle"
      :description="activeConfigDialogDescription"
      :loading-tool-config="loadingToolConfig"
      :current-config-tool="currentConfigTool"
      :config-data="configData"
      :saving-tool-config="savingToolConfig"
      :loading-folders="loadingFolders"
      :mail-folders="mailFolders"
      :mail-folders-error="mailFoldersError"
      :folder-options="folderOptions"
      @update-config-field="updateConfigField"
      @update-ear-excel-file-path="updateEarExcelFilePath"
      @update-invoice-folder-path="updateInvoiceFolderPath"
      @update-invoice-excel-path="updateInvoiceExcelPath"
      @download-ear-template="downloadEarTemplate"
      @load-mail-folders="loadMailFolders"
      @save="saveConfiguration"
    />

    <UiToastStack class="page-toast-stack" :toasts="toasts" @dismiss="dismissToast" />
  </div>
</template>

<style scoped>
.page-shell {
  position: relative;
  min-height: 100vh;
  padding: 1.5rem;
  overflow: visible;
}

.page-shell > *:not(.page-toast-stack) {
  position: relative;
  z-index: 1;
}

.workspace-shell {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 1.25rem;
  align-items: start;
  min-height: calc(100vh - 3rem);
  overflow: visible;
}

.workspace-main {
  display: grid;
  gap: 1.25rem;
  min-height: 0;
  min-width: 0;
  padding-right: 0.25rem;
}

.department-card {
  display: grid;
  gap: 1rem;
}

.workspace-main {
  grid-auto-rows: max-content;
  align-content: start;
}

.dashboard-subtabs {
  min-height: 36px;
}

.app-stable-content {
  min-height: 0;
  overflow: hidden;
}

.dashboard-tab-panel {
  height: 100%;
  overflow-y: auto;
  scrollbar-gutter: stable;
  padding-bottom: 0.25rem;
}

.content-grid {
  align-items: start;
}

.content-grid > .department-card,
.aside-card {
  align-self: start;
}

.content-grid > .department-card {
  grid-template-rows: auto;
}

.tool-grid {
  align-content: start;
  grid-auto-rows: minmax(220px, auto);
}

.aside-card :deep(.log-panel) {
  min-height: 0;
}


.dashboard-subtabs {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.dashboard-subtabs .ui-button {
  min-height: 36px;
  height: 36px;
  align-self: flex-start;
  padding: 0 12px;
}

@media (max-width: 980px) {
  .page-shell {
    padding: 0.85rem;
  }

  .workspace-shell {
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
    min-height: auto;
  }

  .workspace-main {
    width: 100%;
    gap: 0.85rem;
    padding-right: 0;
  }

  .dashboard-subtabs {
    position: sticky;
    top: 8.45rem;
    z-index: 9;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    padding: 0.5rem;
    border: 1px solid var(--border);
    border-radius: 14px;
    background: var(--card);
  }

  .dashboard-subtabs .ui-button {
    width: 100%;
  }

  .app-stable-content,
  .dashboard-tab-panel {
    overflow: visible;
  }

  .content-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 0.85rem;
    margin-top: 0.85rem;
  }

  .department-card {
    padding: 1rem;
  }

  .aside-card {
    position: static;
  }
}

@media (max-width: 560px) {
  .page-shell {
    padding: 0.65rem;
  }

  .dashboard-subtabs {
    top: 8.2rem;
  }
}

</style>

