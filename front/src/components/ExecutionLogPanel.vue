<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import {
  clearDepartmentLogs,
  getDepartmentEventsUrl,
  getDepartmentLogs,
  getToolLogs,
  retryExecution,
  terminateExecution,
} from '../api/index'
import { departments } from '../data/departments'
import UiBadge from './ui/UiBadge.vue'
import UiButton from './ui/UiButton.vue'
import UiCard from './ui/UiCard.vue'
import UiDialog from './ui/UiDialog.vue'
import UiInput from './ui/UiInput.vue'
import UiToastStack from './ui/UiToastStack.vue'

const props = defineProps({
  department: {
    type: String,
    default: null,
  },
  tool: {
    type: String,
    default: null,
  },
  limit: {
    type: Number,
    default: 50,
  },
})

const emit = defineEmits(['task-complete', 'active-tools-change', 'execution-mutated'])

const logs = ref([])
const loading = ref(false)
const error = ref(null)
const searchQuery = ref('')
const statusFilter = ref('all')
const currentPage = ref(1)
const itemsPerPage = 8

const summary = ref({
  queued: 0,
  running: 0,
  failed: 0,
  success: 0,
  terminated: 0,
  cancelling: 0,
})
const streamConnected = ref(false)
const reconnectTimer = ref(null)
const liveRefreshTimer = ref(null)
const liveRefreshInFlight = ref(false)
const pendingExecutions = ref({})
let eventSource = null

const clearDialogOpen = ref(false)
const clearLoading = ref(false)
const detailDialogOpen = ref(false)
const selectedLog = ref(null)
const terminateDialogOpen = ref(false)
const terminateLoading = ref(false)
const terminateTargetId = ref(null)
const retryLoading = ref(false)
const showFailureOutput = ref(false)

const toasts = ref([])
const toastTimers = new Map()
const copySuccess = ref(false)
const hadRunningTasks = ref(false)

function defaultSummary() {
  return {
    queued: 0,
    running: 0,
    failed: 0,
    success: 0,
    terminated: 0,
    cancelling: 0,
  }
}

function isActiveStatus(status) {
  return status === 'queued' || status === 'running' || status === 'cancelling'
}

function getStatusLabel(status) {
  if (status === 'queued') return '排队中'
  if (status === 'running') return '运行中'
  if (status === 'cancelling') return '取消中'
  if (status === 'success') return '已完成'
  if (status === 'terminated') return '已取消'
  return '失败'
}

function getStatusChipClass(status) {
  if (status === 'success') return 'status-success'
  if (status === 'queued' || status === 'running' || status === 'cancelling') return 'status-running'
  return 'status-failed'
}

function getStatusBadgeVariant(status) {
  if (status === 'success') return 'success'
  if (status === 'queued' || status === 'running' || status === 'cancelling') return 'warning'
  return 'danger'
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

function getToolName(toolId) {
  const dept = departments.find((item) => item.code === props.department)
  if (!dept) return toolId
  const tool = dept.tools.find((item) => item.id === toolId)
  return tool?.name || toolId
}

function emitActiveTools() {
  if (!props.department) return

  const toolIds = [...new Set(
    logs.value
      .filter((log) => isActiveStatus(log.status))
      .map((log) => log.tool),
  )]

  emit('active-tools-change', {
    department: props.department,
    toolIds,
  })
}

function updateSummaryFromLogs(nextLogs) {
  const nextSummary = defaultSummary()
  for (const log of nextLogs) {
    if (typeof nextSummary[log.status] === 'number') {
      nextSummary[log.status] += 1
    }
  }
  summary.value = nextSummary
}

function prunePendingExecutions(nextLogs = logs.value) {
  const now = Date.now()
  const nextPending = {}

  for (const [logId, expiresAt] of Object.entries(pendingExecutions.value)) {
    const matchedLog = nextLogs.find((log) => log.id === logId)
    if (matchedLog) {
      if (isActiveStatus(matchedLog.status)) {
        nextPending[logId] = expiresAt
      }
      continue
    }

    if (expiresAt > now) {
      nextPending[logId] = expiresAt
    }
  }

  pendingExecutions.value = nextPending
}

function hasPendingExecutions() {
  return Object.keys(pendingExecutions.value).length > 0
}

function stopLiveRefresh() {
  if (liveRefreshTimer.value) {
    clearTimeout(liveRefreshTimer.value)
    liveRefreshTimer.value = null
  }
}

function shouldKeepLiveRefresh() {
  return Boolean(props.department) && (hasRunningTasks.value || hasPendingExecutions())
}

function scheduleLiveRefresh(delay = 1200) {
  if (liveRefreshTimer.value || !shouldKeepLiveRefresh()) {
    return
  }

  liveRefreshTimer.value = setTimeout(async () => {
    liveRefreshTimer.value = null

    if (!props.department || liveRefreshInFlight.value) {
      if (shouldKeepLiveRefresh()) {
        scheduleLiveRefresh(delay)
      }
      return
    }

    liveRefreshInFlight.value = true
    try {
      await loadLogs({ silent: true })
    } finally {
      liveRefreshInFlight.value = false
      prunePendingExecutions()
      if (shouldKeepLiveRefresh()) {
        scheduleLiveRefresh(delay)
      }
    }
  }, delay)
}

function startTaskLiveRefresh(payload = {}) {
  const logId = typeof payload === 'string' ? null : payload?.logId
  if (logId) {
    pendingExecutions.value = {
      ...pendingExecutions.value,
      [logId]: Date.now() + 30000,
    }
  }

  void loadLogs({ silent: true }).finally(() => {
    prunePendingExecutions()
    scheduleLiveRefresh(800)
  })
}

function syncSnapshot(snapshot) {
  logs.value = Array.isArray(snapshot?.logs) ? snapshot.logs : []
  summary.value = snapshot?.summary || defaultSummary()
  streamConnected.value = true
  prunePendingExecutions(logs.value)
  emitActiveTools()

  if (detailDialogOpen.value && selectedLog.value) {
    const updatedLog = logs.value.find((log) => log.id === selectedLog.value.id)
    if (updatedLog) {
      selectedLog.value = updatedLog
    }
  }
}

async function loadLogs(options = {}) {
  const { silent = false } = options
  if (!props.department) {
    logs.value = []
    summary.value = defaultSummary()
    return
  }

  if (!silent) loading.value = true
  error.value = null

  try {
    const response = props.tool
      ? await getToolLogs(props.department, props.tool, props.limit)
      : await getDepartmentLogs(props.department, props.limit)

    if (!response?.success) {
      throw new Error(response?.error || '无法获取执行记录')
    }

    logs.value = response.logs || []
    updateSummaryFromLogs(logs.value)
    emitActiveTools()

    if (detailDialogOpen.value && selectedLog.value) {
      const updatedLog = logs.value.find((log) => log.id === selectedLog.value.id)
      if (updatedLog) selectedLog.value = updatedLog
    }
  } catch (err) {
    error.value = err.message || '请求失败'
  } finally {
    prunePendingExecutions(logs.value)
    if (shouldKeepLiveRefresh()) {
      scheduleLiveRefresh()
    } else {
      stopLiveRefresh()
    }
    if (!silent) loading.value = false
  }
}

function closeEventStream() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  if (reconnectTimer.value) {
    clearTimeout(reconnectTimer.value)
    reconnectTimer.value = null
  }
}

function scheduleReconnect() {
  if (reconnectTimer.value || !props.department) return
  reconnectTimer.value = setTimeout(() => {
    reconnectTimer.value = null
    connectEventStream()
  }, 2500)
}

function connectEventStream() {
  closeEventStream()
  if (!props.department) return

  const url = getDepartmentEventsUrl(props.department, props.limit)
  eventSource = new EventSource(url)

  eventSource.addEventListener('snapshot', (event) => {
    try {
      syncSnapshot(JSON.parse(event.data))
      error.value = null
    } catch (parseError) {
      console.error('Failed to parse SSE payload:', parseError)
    }
  })

  eventSource.addEventListener('ping', () => {
    streamConnected.value = true
  })

  eventSource.onopen = () => {
    streamConnected.value = true
  }

  eventSource.onerror = () => {
    streamConnected.value = false
    scheduleReconnect()
  }
}

function openTerminateDialog(logId) {
  terminateTargetId.value = logId
  terminateDialogOpen.value = true
}

function closeTerminateDialog() {
  terminateDialogOpen.value = false
  terminateTargetId.value = null
  terminateLoading.value = false
}

async function confirmTerminate() {
  if (!terminateTargetId.value) return

  terminateLoading.value = true
  try {
    const response = await terminateExecution(terminateTargetId.value)
    if (!response?.success) {
      throw new Error(response?.error || '取消任务失败')
    }

    closeTerminateDialog()
    await loadLogs({ silent: true })
    emit('execution-mutated')
    pushToast({
      type: 'success',
      title: '取消请求已发送',
      message: response.message || '任务状态稍后会自动刷新。',
      duration: 3000,
    })
  } catch (err) {
    pushToast({
      type: 'error',
      title: '取消失败',
      message: err.message || '请稍后重试',
      duration: 4000,
    })
  } finally {
    terminateLoading.value = false
  }
}

async function retrySelectedLog() {
  if (!selectedLog.value) return

  retryLoading.value = true
  try {
    const response = await retryExecution(selectedLog.value.id)
    if (!response?.success) {
      throw new Error(response?.error || '重试失败')
    }

    pushToast({
      type: 'success',
      title: '已重新入队',
      message: response.queuePosition
        ? `新的任务已入队，当前排队位置 #${response.queuePosition}。`
        : '新的任务已提交，等待 worker 认领。',
      duration: 3600,
    })
    detailDialogOpen.value = false
    selectedLog.value = null
    await loadLogs({ silent: true })
    emit('execution-mutated')
  } catch (err) {
    pushToast({
      type: 'error',
      title: '重试失败',
      message: err.message || '请稍后再试',
      duration: 4200,
    })
  } finally {
    retryLoading.value = false
  }
}

function openDetailDialog(log) {
  selectedLog.value = log
  detailDialogOpen.value = true
  showFailureOutput.value = false
}

function closeDetailDialog() {
  detailDialogOpen.value = false
  selectedLog.value = null
  showFailureOutput.value = false
}

function openClearDialog() {
  clearDialogOpen.value = true
}

async function confirmClearLogs() {
  if (!props.department) return

  clearLoading.value = true
  try {
    const response = await clearDepartmentLogs(props.department)
    if (!response?.success) {
      throw new Error(response?.error || '清理失败')
    }
    clearDialogOpen.value = false
    pushToast({
      type: 'success',
      title: '历史记录已清理',
      message: response.message || '仅保留排队和运行中的任务。',
      duration: 3000,
    })
    await loadLogs({ silent: true })
    emit('execution-mutated')
  } catch (err) {
    error.value = err.message || '清理失败'
  } finally {
    clearLoading.value = false
  }
}

function formatTime(timestamp) {
  if (!timestamp) return '-'
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return '-'
  return date
    .toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
    .replace(/\//g, '-')
}

function formatDuration(seconds) {
  if (seconds === undefined || seconds === null) return '-'
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)}ms`
  return `${Number(seconds).toFixed(1)}s`
}

function exportLogs() {
  const csvContent = [
    ['执行时间', '任务', '状态', '耗时', '输出'],
    ...filteredLogs.value.map((log) => [
      formatTime(log.timestamp),
      getToolName(log.tool),
      getStatusLabel(log.status),
      formatDuration(log.duration),
      (log.output || '').replace(/\n/g, ' '),
    ]),
  ]
    .map((row) => row.map((cell) => `"${cell}"`).join(','))
    .join('\n')

  const blob = new Blob([`\ufeff${csvContent}`], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `执行记录_${props.department}_${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
}

async function copyError() {
  const text = selectedLog.value?.error || selectedLog.value?.output
  if (!text) return

  try {
    await navigator.clipboard.writeText(text)
    copySuccess.value = true
    setTimeout(() => {
      copySuccess.value = false
    }, 1500)
  } catch {
    pushToast({
      type: 'error',
      title: '复制失败',
      message: '浏览器未允许剪贴板写入。',
      duration: 3000,
    })
  }
}

const baseLogs = computed(() => {
  if (!props.tool) return logs.value
  return logs.value.filter((log) => log.tool === props.tool)
})

const filteredLogs = computed(() => {
  let result = baseLogs.value

  if (statusFilter.value !== 'all') {
    result = result.filter((log) => log.status === statusFilter.value)
  }

  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter((log) => {
      const toolName = getToolName(log.tool).toLowerCase()
      const output = (log.output || '').toLowerCase()
      const errorText = (log.error || '').toLowerCase()
      return toolName.includes(query) || output.includes(query) || errorText.includes(query)
    })
  }

  return result
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredLogs.value.length / itemsPerPage)))

const displayedLogs = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage
  return filteredLogs.value.slice(start, start + itemsPerPage)
})

const hasRunningTasks = computed(() => logs.value.some((log) => isActiveStatus(log.status)))

const summaryCards = computed(() => [
  {
    label: '运行中',
    value: summary.value.running + summary.value.cancelling,
    variant: 'warning',
  },
  {
    label: '排队中',
    value: summary.value.queued,
    variant: 'secondary',
  },
  {
    label: '失败',
    value: summary.value.failed,
    variant: 'danger',
  },
  {
    label: '已完成',
    value: summary.value.success,
    variant: 'success',
  },
])

watch(
  () => props.department,
  async () => {
    currentPage.value = 1
    hadRunningTasks.value = false
    pendingExecutions.value = {}
    stopLiveRefresh()
    emit('active-tools-change', {
      department: props.department,
      toolIds: [],
    })
    await loadLogs()
    hadRunningTasks.value = hasRunningTasks.value
    connectEventStream()
  },
  { immediate: true },
)

watch([searchQuery, statusFilter], () => {
  currentPage.value = 1
})

watch(
  () => logs.value,
  (newLogs) => {
    prunePendingExecutions(newLogs)
    emitActiveTools()
    const hasRunning = newLogs.some((log) => isActiveStatus(log.status))
    if (hadRunningTasks.value && !hasRunning) {
      emit('task-complete')
    }
    hadRunningTasks.value = hasRunning

    if (shouldKeepLiveRefresh()) {
      scheduleLiveRefresh()
    } else {
      stopLiveRefresh()
    }
  },
  { deep: true },
)

onUnmounted(() => {
  closeEventStream()
  stopLiveRefresh()
  for (const timer of toastTimers.values()) {
    clearTimeout(timer)
  }
  toastTimers.clear()
})

defineExpose({
  refresh: loadLogs,
  exportLogs,
  onTaskStarted: (payload) => {
    const toolId = typeof payload === 'string' ? payload : payload?.toolId
    hadRunningTasks.value = true
    startTaskLiveRefresh(payload)
    if (toolId && props.department) {
      const current = new Set(
        logs.value
          .filter((log) => isActiveStatus(log.status))
          .map((log) => log.tool),
      )
      current.add(toolId)
      emit('active-tools-change', {
        department: props.department,
        toolIds: [...current],
      })
    }
  },
})
</script>

<template>
  <UiCard class="log-panel">
    <div class="panel-header">
      <div class="panel-copy">
        <div class="panel-title-row">
          <h3 class="panel-title">运行记录</h3>
          <UiBadge :variant="streamConnected ? 'success' : 'warning'">
            {{ streamConnected ? '实时已连接' : '实时重连中' }}
          </UiBadge>
        </div>
        <p class="panel-subtitle">优先看正在跑的任务和最近结果，完整细节仍然可以点开查看。</p>
      </div>

      <div class="panel-actions">
        <UiButton variant="outline" :loading="loading" @click="loadLogs">
          刷新
        </UiButton>
        <UiButton variant="outline" :disabled="filteredLogs.length === 0" @click="exportLogs">
          导出
        </UiButton>
        <UiButton variant="outline" :disabled="logs.length === 0" @click="openClearDialog">
          清空
        </UiButton>
      </div>
    </div>

    <div class="summary-strip">
      <div v-for="card in summaryCards" :key="card.label" class="summary-pill">
        <span class="summary-pill-label">{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
      </div>
    </div>

    <div class="filters">
      <UiInput v-model="searchQuery" placeholder="搜索任务名或错误信息" class="search-input" />

      <div class="status-filter">
        <button
          v-for="option in [
            { value: 'all', label: '全部' },
            { value: 'queued', label: '排队中' },
            { value: 'running', label: '运行中' },
            { value: 'success', label: '已完成' },
            { value: 'failed', label: '失败' },
          ]"
          :key="option.value"
          class="filter-btn"
          :class="{ active: statusFilter === option.value }"
          @click="statusFilter = option.value"
        >
          {{ option.label }}
        </button>
      </div>
    </div>

    <div v-if="error" class="panel-error">
      {{ error }}
    </div>

    <div v-else-if="displayedLogs.length === 0" class="panel-empty">
      {{ searchQuery || statusFilter !== 'all' ? '没有匹配的记录' : hasRunningTasks ? '任务正在排队或运行中...' : '暂无执行记录' }}
    </div>

    <div v-else class="records-shell">
      <button
        v-for="log in displayedLogs"
        :key="log.id"
        type="button"
        class="record-card"
        :class="{
          'record-card-success': log.status === 'success',
          'record-card-running': log.status === 'queued' || log.status === 'running' || log.status === 'cancelling',
          'record-card-failed': !['success', 'queued', 'running', 'cancelling'].includes(log.status),
        }"
        @click="openDetailDialog(log)"
      >
        <div class="record-card-top">
          <div class="task-cell">
            <span class="task-name">{{ getToolName(log.tool) }}</span>
            <span class="task-meta">{{ formatTime(log.timestamp) }}</span>
          </div>
          <span class="status-chip" :class="getStatusChipClass(log.status)">
            <span class="status-dot"></span>
            <span>{{ getStatusLabel(log.status) }}</span>
          </span>
        </div>

        <div class="record-card-bottom">
          <span>{{ log.queuePosition ? `队列 #${log.queuePosition}` : '非排队任务' }}</span>
          <span>{{ formatDuration(log.duration) }}</span>
        </div>
      </button>
    </div>

    <div v-if="totalPages > 1" class="pagination">
      <button class="page-btn" :disabled="currentPage === 1" @click="currentPage -= 1">上一页</button>
      <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
      <button class="page-btn" :disabled="currentPage === totalPages" @click="currentPage += 1">下一页</button>
    </div>

    <UiDialog
      v-model:open="detailDialogOpen"
      size="wide"
      :title="selectedLog ? getToolName(selectedLog.tool) : '执行详情'"
      @update:open="!$event && closeDetailDialog()"
    >
      <div v-if="selectedLog" class="detail-shell">
        <div class="detail-meta-grid">
          <div class="meta-card">
            <span class="meta-label">开始时间</span>
            <strong>{{ formatTime(selectedLog.timestamp) }}</strong>
          </div>
          <div class="meta-card">
            <span class="meta-label">状态</span>
            <UiBadge :variant="getStatusBadgeVariant(selectedLog.status)">
              {{ getStatusLabel(selectedLog.status) }}
            </UiBadge>
          </div>
          <div class="meta-card">
            <span class="meta-label">耗时</span>
            <strong>{{ formatDuration(selectedLog.duration) }}</strong>
          </div>
          <div class="meta-card">
            <span class="meta-label">排队位置</span>
            <strong>{{ selectedLog.queuePosition ? `#${selectedLog.queuePosition}` : '-' }}</strong>
          </div>
        </div>

        <div class="detail-toolbar">
          <UiBadge variant="secondary">尝试次数 {{ selectedLog.attempt || 1 }}</UiBadge>
          <div class="detail-actions">
            <UiButton
              v-if="['failed', 'terminated'].includes(selectedLog.status)"
              variant="outline"
              :loading="retryLoading"
              @click="retrySelectedLog"
            >
              失败重试
            </UiButton>
            <UiButton
              v-if="isActiveStatus(selectedLog.status)"
              variant="danger"
              @click="openTerminateDialog(selectedLog.id)"
            >
              取消任务
            </UiButton>
          </div>
        </div>

        <div v-if="isActiveStatus(selectedLog.status)" class="detail-section">
          <div class="section-header">
            <h4>实时输出</h4>
            <UiBadge variant="warning">{{ getStatusLabel(selectedLog.status) }}</UiBadge>
          </div>
          <pre class="log-output live-output">{{ selectedLog.output || selectedLog.error || '等待 worker 输出...' }}</pre>
        </div>

        <div v-if="selectedLog.error" class="detail-section">
          <div class="section-header">
            <h4>错误信息</h4>
            <UiButton variant="outline" @click="copyError">
              {{ copySuccess ? '已复制' : '复制错误' }}
            </UiButton>
          </div>
          <pre class="log-error-detail">{{ selectedLog.error }}</pre>
        </div>

        <div v-if="selectedLog.output && !isActiveStatus(selectedLog.status)" class="detail-section">
          <div class="section-header">
            <h4>执行输出</h4>
            <UiButton
              v-if="['failed', 'terminated'].includes(selectedLog.status)"
              variant="outline"
              @click="showFailureOutput = !showFailureOutput"
            >
              {{ showFailureOutput ? '收起输出' : '展开输出' }}
            </UiButton>
          </div>
          <pre v-if="selectedLog.status === 'success' || showFailureOutput" class="log-output">{{ selectedLog.output }}</pre>
        </div>
      </div>

      <template #footer>
        <UiButton variant="outline" @click="closeDetailDialog">关闭</UiButton>
      </template>
    </UiDialog>

    <UiDialog
      v-model:open="clearDialogOpen"
      title="清理历史记录"
      description="只会清理已结束的执行记录，排队中和运行中的任务会保留。"
    >
      <template #footer>
        <UiButton variant="outline" :disabled="clearLoading" @click="clearDialogOpen = false">取消</UiButton>
        <UiButton :loading="clearLoading" @click="confirmClearLogs">确认清理</UiButton>
      </template>
    </UiDialog>

    <UiDialog
      v-model:open="terminateDialogOpen"
      title="取消任务"
      description="任务会先标记为取消中，由 worker 安全终止当前脚本进程。"
    >
      <template #footer>
        <UiButton variant="outline" :disabled="terminateLoading" @click="closeTerminateDialog">关闭</UiButton>
        <UiButton variant="danger" :loading="terminateLoading" @click="confirmTerminate">确认取消</UiButton>
      </template>
    </UiDialog>
  </UiCard>

  <UiToastStack :toasts="toasts" @dismiss="dismissToast" />
</template>

<style scoped>
.log-panel {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
  flex-wrap: wrap;
}

.panel-copy {
  display: grid;
  gap: 0.5rem;
}

.panel-title-row {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  flex-wrap: wrap;
}

.panel-title {
  margin: 0;
  font-size: 1.18rem;
  line-height: 1.1;
}

.panel-subtitle {
  color: var(--muted-foreground);
  font-size: 0.9rem;
}

.panel-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.summary-strip {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.6rem;
}

.summary-pill {
  border: 1px solid var(--border);
  border-radius: 1rem;
  background: var(--card-muted);
  padding: 0.8rem 0.85rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.summary-pill-label {
  color: var(--muted);
  font-size: 0.74rem;
  letter-spacing: 0.02em;
}

.summary-pill strong {
  font-size: 1rem;
  line-height: 1;
}

.filters {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.search-input {
  flex: 1;
  min-width: 220px;
}

.status-filter {
  display: flex;
  gap: 0.35rem;
  flex-wrap: wrap;
}

.filter-btn,
.page-btn {
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 0.45rem 0.8rem;
  background: var(--card-muted);
  color: var(--muted-foreground);
  cursor: pointer;
  transition: 0.18s ease;
}

.filter-btn:hover,
.page-btn:hover:not(:disabled) {
  border-color: var(--border-strong);
  color: var(--foreground);
}

.filter-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-foreground);
}

.panel-error,
.panel-empty {
  padding: 1rem;
  border: 1px dashed var(--border);
  border-radius: 1rem;
  color: var(--muted-foreground);
  text-align: center;
}

.panel-error {
  color: var(--danger);
  border-color: var(--danger-border);
  background: var(--danger-soft);
}

.records-shell {
  border: 1px solid var(--border);
  border-radius: 1rem;
  background: var(--card-muted);
  padding: 0.55rem;
  display: grid;
  gap: 0.5rem;
  max-height: min(58vh, 720px);
  overflow: auto;
}

.record-card {
  width: 100%;
  border: 1px solid transparent;
  border-radius: 0.9rem;
  padding: 0.85rem;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
}

.record-card:hover {
  border-color: var(--border-strong);
  box-shadow: 0 0 0 3px var(--ring);
  transform: translateY(-1px);
}

.record-card-success {
  background: linear-gradient(0deg, var(--success-soft), var(--success-soft));
}

.record-card-running {
  background: linear-gradient(0deg, var(--warning-soft), var(--warning-soft));
}

.record-card-failed {
  background: linear-gradient(0deg, var(--danger-soft), var(--danger-soft));
}

.record-card-top {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 0.75rem;
}

.record-card-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.75rem;
  color: var(--muted-foreground);
  font-size: 0.8rem;
}

.task-cell {
  display: grid;
  gap: 0.28rem;
}

.task-name {
  font-weight: 600;
  line-height: 1.45;
}

.task-meta {
  color: var(--muted);
  font-size: 0.78rem;
}

.status-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  font-weight: 600;
}

.status-success {
  color: var(--success);
}

.status-running {
  color: var(--warning);
}

.status-failed {
  color: var(--danger);
}

.status-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 999px;
  background: currentColor;
}

.queue-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 2.4rem;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  background: var(--secondary);
  color: var(--foreground);
  font-weight: 600;
}

.queue-empty {
  color: var(--muted);
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 1rem;
}

.page-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.page-info {
  color: var(--muted);
  font-size: 0.85rem;
}

.detail-shell {
  display: grid;
  gap: 1rem;
}

.detail-meta-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.75rem;
}

.meta-card {
  border: 1px solid var(--border);
  border-radius: 1rem;
  padding: 0.85rem 0.95rem;
  background: var(--card-muted);
  display: grid;
  gap: 0.45rem;
}

.meta-label {
  color: var(--muted);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.detail-toolbar,
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.detail-actions {
  display: flex;
  gap: 0.625rem;
  flex-wrap: wrap;
}

.detail-section {
  display: grid;
  gap: 0.75rem;
}

.detail-section h4 {
  margin: 0;
  font-size: 0.95rem;
}

.log-output,
.log-error-detail {
  margin: 0;
  padding: 0.95rem 1rem;
  border-radius: 1rem;
  border: 1px solid var(--border);
  background: var(--card-muted);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.55;
  font-size: 0.85rem;
}

.live-output {
  min-height: 14rem;
  max-height: 26rem;
  overflow: auto;
}

.log-error-detail {
  background: var(--danger-soft);
  border-color: var(--danger-border);
  color: var(--danger);
}

@media (max-width: 980px) {
  .summary-strip,
  .detail-meta-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .summary-strip,
  .detail-meta-grid {
    grid-template-columns: 1fr;
  }
}
</style>
