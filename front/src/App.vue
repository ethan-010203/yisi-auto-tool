<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getData, getToolConfig, getToolPreview, runDepartmentTool, saveConfig } from './api/index'
import ExecutionLogPanel from './components/ExecutionLogPanel.vue'
import ToolPreviewDialog from './components/preview/ToolPreviewDialog.vue'
import UiBadge from './components/ui/UiBadge.vue'
import UiButton from './components/ui/UiButton.vue'
import UiCard from './components/ui/UiCard.vue'
import UiDialog from './components/ui/UiDialog.vue'
import UiFileInput from './components/ui/UiFileInput.vue'
import UiLabel from './components/ui/UiLabel.vue'
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
    // localStorage 不可用，使用默认值
  }
  return departments[0].code
}

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

const configData = ref({
  folderPath: '',
  excelPath: '',
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
  const hasFolder = Boolean(configData.value.folderPath)
  const hasExcel = Boolean(configData.value.excelPath)

  if (hasFolder && hasExcel) {
    return '已配置完成'
  }

  if (hasFolder || hasExcel) {
    return '部分已配置'
  }

  return '待配置'
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

async function loadInvoiceConfig() {
  try {
    const response = await getToolConfig(PREVIEW_DEPARTMENT, PREVIEW_TOOL_ID)
    if (response?.success && response.config) {
      configData.value = {
        folderPath: response.config.folderPath || '',
        excelPath: response.config.excelPath || '',
      }
    }
  } catch (error) {
    console.error('Failed to load config:', error)
  }
}

async function saveConfiguration() {
  try {
    const response = await saveConfig(PREVIEW_DEPARTMENT, PREVIEW_TOOL_ID, configData.value)
    if (!response?.success) {
      throw new Error(response?.error || '保存失败')
    }

    configDialogOpen.value = false
    pushToast({
      type: 'success',
      title: '配置已保存',
      message: '识别目录和 Excel 输出位置已经更新。',
    })

    previewCache.delete(getToolKey(PREVIEW_DEPARTMENT, PREVIEW_TOOL_ID))
    if (previewDialogOpen.value && previewTargetKey.value === getToolKey(PREVIEW_DEPARTMENT, PREVIEW_TOOL_ID)) {
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

  try {
    const result = await runDepartmentTool(activeDepartmentCode.value, tool.id)
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
    runningToolId.value = ''
    // 刷新执行日志
    logPanel.value?.refresh()
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
        <UiBadge variant="secondary">Department Workspace</UiBadge>
        <h1>部门工具工作台</h1>
        <p class="page-lead">
          这次升级把顾问部“英德单据识别”的体验重点放在预览流畅度上，让页面先响应，再异步补数据。
        </p>
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
        <p class="section-note">
          预览能力会在顾问部页签激活时提前预热，这样点击“预览”时不会再把等待感全部留给用户。
        </p>
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
                  <UiButton v-if="tool.configurable" variant="outline" @click="configDialogOpen = true">
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
                  @click="configDialogOpen = true"
                >
                  配置
                </UiButton>
                <UiButton
                  :loading="runningToolId === tool.id"
                  @click="runDepartmentScript(tool)"
                >
                  执行测试
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
      title="英德单据识别配置"
      description="将识别源目录和 Excel 输出路径整理为独立配置，避免每次运行时重新输入。"
    >
      <div class="config-form">
        <div class="form-field">
          <UiLabel for="folder-path">源单据文件夹</UiLabel>
          <UiFileInput
            id="folder-path"
            v-model="configData.folderPath"
            placeholder="选择需要识别的单据目录..."
            webkitdirectory
          />
        </div>

        <div class="form-field">
          <UiLabel for="excel-path">Excel 输出文件</UiLabel>
          <UiFileInput
            id="excel-path"
            v-model="configData.excelPath"
            placeholder="选择 Excel 输出位置..."
            accept=".xlsx,.xls"
          />
        </div>
      </div>

      <template #footer>
        <UiButton variant="outline" @click="configDialogOpen = false">取消</UiButton>
        <UiButton @click="saveConfiguration">保存配置</UiButton>
      </template>
    </UiDialog>

    <UiToastStack :toasts="toasts" @dismiss="dismissToast" />
  </div>
</template>
