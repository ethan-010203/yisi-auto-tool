<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { clearDepartmentLogs, getDepartmentLogs, getToolLogs, terminateExecution } from '../api/index'
import { departments } from '../data/departments'
import UiBadge from './ui/UiBadge.vue'
import UiButton from './ui/UiButton.vue'
import UiCard from './ui/UiCard.vue'
import UiDialog from './ui/UiDialog.vue'
import UiInput from './ui/UiInput.vue'
import UiToastStack from './ui/UiToastStack.vue'

const logs = ref([])
const loading = ref(false)
const error = ref(null)
const currentPage = ref(1)
const itemsPerPage = 10
const searchQuery = ref('')
const statusFilter = ref('all')

const pollInterval = ref(null)
const POLL_DELAY = 1000

const clearDialogOpen = ref(false)
const clearLoading = ref(false)
const detailDialogOpen = ref(false)
const selectedLog = ref(null)
const terminateDialogOpen = ref(false)
const terminateLoading = ref(false)
const terminateTargetId = ref(null)
const showFailureOutput = ref(false)

const toasts = ref([])
const toastTimers = new Map()
const copySuccess = ref(false)
const hadRunningTasks = ref(false)

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

const emit = defineEmits(['task-complete', 'active-tools-change'])

function isActiveStatus(status) {
  return status === 'queued' || status === 'running'
}

function getStatusLabel(status) {
  if (status === 'queued') return '排队中'
  if (status === 'running') return '运行中'
  if (status === 'success') return '成功'
  if (status === 'terminated') return '已终止'
  return '失败'
}

function getStatusChipClass(status) {
  if (status === 'success') return 'status-success'
  if (status === 'queued' || status === 'running') return 'status-running'
  return 'status-failed'
}

function getStatusBadgeVariant(status) {
  if (status === 'success') return 'success'
  if (status === 'queued' || status === 'running') return 'warning'
  return 'danger'
}

const hasRunningTasks = computed(() => logs.value.some((log) => isActiveStatus(log.status)))

const filteredLogs = computed(() => {
  let result = logs.value

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

function getToolName(toolId) {
  const dept = departments.find((item) => item.code === props.department)
  if (!dept) return toolId
  const tool = dept.tools.find((item) => item.id === toolId)
  return tool?.name || toolId
}

function emitActiveTools() {
  if (!props.department) {
    return
  }

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

async function loadLogs(options = {}) {
  const { silent = false } = options
  if (!props.department) {
    logs.value = []
    return
  }

  if (!silent) {
    loading.value = true
  }
  error.value = null

  try {
    const response = props.tool
      ? await getToolLogs(props.department, props.tool, props.limit)
      : await getDepartmentLogs(props.department, props.limit)

    if (response?.success) {
      logs.value = response.logs || []
      emitActiveTools()

      if (detailDialogOpen.value && selectedLog.value) {
        const updatedLog = logs.value.find((log) => log.id === selectedLog.value.id)
        if (updatedLog) {
          selectedLog.value = updatedLog
        }
      }
    } else {
      error.value = response?.error || '加载失败'
    }
  } catch (err) {
    error.value = err.message || '网络错误'
  } finally {
    if (!silent) {
      loading.value = false
    }
  }
}

function startPolling() {
  stopPolling()
  pollInterval.value = setInterval(() => {
    loadLogs({ silent: true })
  }, POLL_DELAY)
}

function stopPolling() {
  if (pollInterval.value) {
    clearInterval(pollInterval.value)
    pollInterval.value = null
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
    if (response?.success) {
      closeTerminateDialog()
      detailDialogOpen.value = false
      selectedLog.value = null

      setTimeout(() => {
        loadLogs()
      }, 100)

      pushToast({
        type: 'success',
        title: '任务已终止',
        message: '任务已成功终止，并已写入执行记录。',
        duration: 3000,
      })
    } else {
      pushToast({
        type: 'error',
        title: '终止失败',
        message: response?.error || '无法终止任务。',
        duration: 4000,
      })
    }
  } catch (err) {
    pushToast({
      type: 'error',
      title: '网络错误',
      message: err.message || '请检查网络连接后重试。',
      duration: 4000,
    })
  } finally {
    terminateLoading.value = false
  }
}

function openClearDialog() {
  clearDialogOpen.value = true
}

function openDetailDialog(log) {
  selectedLog.value = log
  detailDialogOpen.value = true
  showFailureOutput.value = false

  if (isActiveStatus(log.status)) {
    loadLogs()
  }
}

function closeDetailDialog() {
  detailDialogOpen.value = false
  selectedLog.value = null
  showFailureOutput.value = false
}

async function confirmClearLogs() {
  if (!props.department) return

  clearLoading.value = true
  try {
    const response = await clearDepartmentLogs(props.department)
    if (response?.success) {
      logs.value = []
      currentPage.value = 1
      clearDialogOpen.value = false
    } else {
      error.value = response?.error || '清空失败'
    }
  } catch (err) {
    error.value = err.message || '网络错误'
  } finally {
    clearLoading.value = false
  }
}

function exportLogs() {
  const csvContent = [
    ['执行时间', '任务名称', '状态', '执行时长', '输出'],
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

  const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `执行记录_${props.department}_${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
}

function prevPage() {
  if (currentPage.value > 1) {
    currentPage.value -= 1
  }
}

function nextPage() {
  if (currentPage.value < totalPages.value) {
    currentPage.value += 1
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

function formatEndTime(timestamp, duration) {
  if (!timestamp || duration === undefined || duration === null) return '-'
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return '-'

  return new Date(date.getTime() + duration * 1000)
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
  return `${seconds.toFixed(1)}s`
}

async function copyError() {
  const text = selectedLog.value?.error || selectedLog.value?.output
  if (!text) return

  try {
    const blob = new Blob([text], { type: 'text/plain' })
    const clipboardItem = new ClipboardItem({ 'text/plain': blob })
    await navigator.clipboard.write([clipboardItem])
    copySuccess.value = true
    setTimeout(() => {
      copySuccess.value = false
    }, 1500)
  } catch {
    try {
      await navigator.clipboard.writeText(text)
      copySuccess.value = true
      setTimeout(() => {
        copySuccess.value = false
      }, 1500)
    } catch {
      const ok = fallbackCopy(text)
      if (ok) {
        copySuccess.value = true
        setTimeout(() => {
          copySuccess.value = false
        }, 1500)
      } else {
        pushToast({
          type: 'error',
          title: '复制失败',
          message: '请手动复制错误内容。',
          duration: 3000,
        })
      }
    }
  }
}

function fallbackCopy(text) {
  const el = document.createElement('textarea')
  el.value = text
  el.style.cssText = 'position:fixed;left:-9999px;top:0;'
  document.body.appendChild(el)

  const selection = window.getSelection()
  const range = document.createRange()
  range.selectNode(el)
  selection?.removeAllRanges()
  selection?.addRange(range)

  el.select()
  el.setSelectionRange(0, el.value.length)

  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }

  selection?.removeAllRanges()
  document.body.removeChild(el)
  return ok
}

watch(
  () => props.department,
  () => {
    currentPage.value = 1
    hadRunningTasks.value = false
    emit('active-tools-change', {
      department: props.department,
      toolIds: [],
    })
    loadLogs().then(() => {
      hadRunningTasks.value = hasRunningTasks.value
      if (hasRunningTasks.value) {
        startPolling()
      }
    })
  },
  { immediate: true },
)

watch([searchQuery, statusFilter], () => {
  currentPage.value = 1
})

watch(
  () => logs.value,
  (newLogs) => {
    emitActiveTools()
    const hasRunning = newLogs.some((log) => isActiveStatus(log.status))
    if (hasRunning && !pollInterval.value) {
      startPolling()
    } else if (!hasRunning && pollInterval.value) {
      stopPolling()
    }

    if (hadRunningTasks.value && !hasRunning) {
      emit('task-complete')
    }
    hadRunningTasks.value = hasRunning
  },
  { deep: true },
)

onMounted(() => {
  if (props.department) {
    loadLogs().then(() => {
      hadRunningTasks.value = hasRunningTasks.value
    })
  }
})

onUnmounted(() => {
  stopPolling()
  for (const timer of toastTimers.values()) {
    clearTimeout(timer)
  }
  toastTimers.clear()
})

defineExpose({
  refresh: loadLogs,
  exportLogs,
  onTaskStarted: (toolId) => {
    hadRunningTasks.value = true
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
    if (!pollInterval.value) {
      startPolling()
    }
  },
})
</script>

<template>
  <UiCard class="log-panel">
    <div class="log-header">
      <div>
        <div class="log-title-wrapper">
          <h3 class="log-title">执行记录</h3>
        </div>
        <span v-if="filteredLogs.length > 0" class="log-count">共 {{ filteredLogs.length }} 条记录</span>
      </div>

      <div class="log-actions">
        <UiButton
          v-if="false"
          variant="outline"
          :loading="clearLoading"
          :disabled="loading || logs.length === 0"
          @click="openClearDialog"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 6px;">
            <path d="M3 6h18" />
            <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
            <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
          </svg>
          清空
        </UiButton>

        <UiButton variant="outline" :loading="loading" @click="loadLogs">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 6px;">
            <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
            <path d="M3 3v5h5" />
            <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
            <path d="M16 16h5v5" />
          </svg>
          刷新
        </UiButton>
      </div>
    </div>

    <div class="log-filter-bar">
      <UiInput v-model="searchQuery" placeholder="搜索任务名称或日志内容..." class="search-input" />

      <div class="status-filter">
        <button
          v-for="option in [
            { value: 'all', label: '全部' },
            { value: 'queued', label: '排队中' },
            { value: 'running', label: '运行中' },
            { value: 'success', label: '成功' },
            { value: 'failed', label: '失败' },
            { value: 'terminated', label: '已终止' },
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

    <div v-if="loading" class="log-loading">
      <div v-for="i in 5" :key="i" class="log-skeleton" />
    </div>

    <div v-else-if="error" class="log-error">
      <p>{{ error }}</p>
    </div>

    <div v-else-if="displayedLogs.length === 0" class="log-empty">
      <p>{{ searchQuery || statusFilter !== 'all' ? '没有找到匹配的记录' : hasRunningTasks ? '任务正在排队或运行中...' : '暂无执行记录' }}</p>
    </div>

    <div v-else class="log-table-container">
      <table class="log-table">
        <thead>
          <tr>
            <th class="col-task">
              <div class="header-cell">
                <span>任务</span>
              </div>
            </th>
            <th class="col-status">
              <div class="header-cell header-cell-status">
                <span>结果</span>
              </div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="log in displayedLogs"
            :key="log.id"
            class="log-row-clickable"
            :class="{
              'log-row-success': log.status === 'success',
              'log-row-running': log.status === 'queued' || log.status === 'running',
              'log-row-failed': log.status !== 'success' && log.status !== 'queued' && log.status !== 'running',
            }"
            @click="openDetailDialog(log)"
          >
            <td class="col-task">
              <span class="task-name" :title="getToolName(log.tool)">{{ getToolName(log.tool) }}</span>
            </td>
            <td class="col-status status-cell">
              <span
                :class="[
                  'status-chip',
                  getStatusChipClass(log.status),
                ]"
              >
                <span class="status-dot"></span>
                <span>{{ getStatusLabel(log.status) }}</span>
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="totalPages > 1" class="log-pagination">
      <button class="page-btn" :disabled="currentPage === 1" @click="prevPage">上一页</button>
      <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
      <button class="page-btn" :disabled="currentPage === totalPages" @click="nextPage">下一页</button>
    </div>

    <UiDialog
      v-model:open="clearDialogOpen"
      title="清空执行记录"
      description="确定要清空当前部门的全部执行记录吗？此操作无法撤销。"
    >
      <template #footer>
        <UiButton variant="outline" :disabled="clearLoading" @click="clearDialogOpen = false">取消</UiButton>
        <UiButton :loading="clearLoading" @click="confirmClearLogs">确认清空</UiButton>
      </template>
    </UiDialog>

    <UiDialog
      v-model:open="detailDialogOpen"
      size="wide"
      :title="selectedLog ? getToolName(selectedLog.tool) : '日志详情'"
      @update:open="!$event && closeDetailDialog()"
    >
      <div v-if="selectedLog" class="log-detail-content">
        <div class="detail-header">
          <div class="detail-meta">
            <div class="meta-item">
              <span class="meta-label">执行时间</span>
              <span class="meta-value">{{ formatTime(selectedLog.timestamp) }}</span>
            </div>

            <div class="meta-item">
              <span class="meta-label">执行结果</span>
              <UiBadge :variant="getStatusBadgeVariant(selectedLog.status)">
                {{ getStatusLabel(selectedLog.status) }}
              </UiBadge>
            </div>

            <div class="meta-item">
              <span class="meta-label">执行时长</span>
              <span class="meta-value">{{ formatDuration(selectedLog.duration) }}</span>
            </div>

            <div class="meta-item">
              <span class="meta-label">结束时间</span>
              <span class="meta-value">{{ isActiveStatus(selectedLog.status) ? '-' : formatEndTime(selectedLog.timestamp, selectedLog.duration) }}</span>
            </div>

            <div v-if="selectedLog.queuePosition" class="meta-item">
              <span class="meta-label">排队位置</span>
              <span class="meta-value">#{{ selectedLog.queuePosition }}</span>
            </div>
          </div>
        </div>

        <div v-if="isActiveStatus(selectedLog.status)" class="detail-section running-toolbar">
          <div class="running-indicator">
            <div class="spinner"></div>
            <span>{{ selectedLog.status === 'queued' ? '任务正在排队中...' : '任务正在执行中...' }}</span>
          </div>
          <div class="running-actions">
            <span class="live-log-hint">每 1 秒自动刷新</span>
            <UiButton variant="danger" size="sm" @click="openTerminateDialog(selectedLog.id)">终止执行</UiButton>
          </div>
        </div>

        <div v-if="isActiveStatus(selectedLog.status)" class="detail-section">
          <div class="section-header">
            <h4 class="section-title">{{ selectedLog.status === 'queued' ? '排队状态' : '实时输出' }}</h4>
          </div>
          <pre class="log-output log-output-live">{{ selectedLog.output || selectedLog.error || (selectedLog.status === 'queued' ? '任务已进入队列，等待可用执行槽位...' : '任务已启动，等待日志输出...') }}</pre>
        </div>

        <div v-if="selectedLog.status === 'success' && selectedLog.output" class="detail-section">
          <h4 class="section-title">输出日志</h4>
          <pre class="log-output">{{ selectedLog.output }}</pre>
        </div>

        <div v-if="selectedLog.error" class="detail-section">
          <div class="section-header">
            <h4 class="section-title error-title">错误信息</h4>
            <button class="copy-btn" :class="{ 'copy-success': copySuccess }" @click="copyError" title="复制错误信息">
              <svg v-if="!copySuccess" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
              <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              {{ copySuccess ? '已复制' : '复制' }}
            </button>
          </div>
          <pre class="log-error-detail">{{ selectedLog.error }}</pre>
        </div>

        <div v-if="['failed', 'terminated'].includes(selectedLog.status) && selectedLog.output" class="detail-section">
          <div class="section-header">
            <div class="detail-section-heading">
              <h4 class="section-title">运行日志</h4>
              <UiBadge variant="outline">可展开查看</UiBadge>
            </div>
            <UiButton variant="outline" @click="showFailureOutput = !showFailureOutput">
              {{ showFailureOutput ? '收起日志' : '查看运行日志' }}
            </UiButton>
          </div>
          <div v-if="showFailureOutput" class="log-output-shell">
            <pre class="log-output">{{ selectedLog.output }}</pre>
          </div>
        </div>

        <div v-if="!isActiveStatus(selectedLog.status) && !selectedLog.output && !selectedLog.error" class="detail-section empty">
          <p>没有输出日志</p>
        </div>
      </div>

      <template #footer>
        <UiButton variant="outline" @click="closeDetailDialog">关闭</UiButton>
      </template>
    </UiDialog>

    <UiDialog
      v-model:open="terminateDialogOpen"
      title="确认终止任务"
      description="确定要终止当前正在运行的任务吗？此操作无法撤销。"
    >
      <template #footer>
        <UiButton variant="outline" :disabled="terminateLoading" @click="closeTerminateDialog">取消</UiButton>
        <UiButton variant="danger" :loading="terminateLoading" @click="confirmTerminate">确认终止</UiButton>
      </template>
    </UiDialog>
  </UiCard>

  <UiToastStack :toasts="toasts" @dismiss="dismissToast" />
</template>

<style scoped>
.log-panel {
  padding: 20px;
}

.detail-section-heading {
  display: flex;
  align-items: center;
  gap: 8px;
}

.log-output-shell {
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  background: hsl(var(--muted) / 0.35);
  padding: 0;
  overflow: hidden;
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
  gap: 12px;
}

.log-header > div:first-child {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.log-title-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
}

.log-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--foreground);
  white-space: nowrap;
  flex-shrink: 0;
}

.log-count {
  font-size: 0.875rem;
  color: var(--muted);
  white-space: nowrap;
}

.log-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.log-actions .ui-button {
  flex-shrink: 0;
}

.log-filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.search-input {
  flex: 1;
  min-width: 200px;
}

.status-filter {
  display: flex;
  gap: 4px;
}

.filter-btn {
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--card-muted);
  font-size: 0.875rem;
  color: var(--muted-foreground);
  cursor: pointer;
  transition: all 0.15s ease;
}

.filter-btn:hover {
  border-color: var(--border-strong);
  color: var(--foreground);
}

.filter-btn.active {
  background: var(--accent);
  color: var(--accent-foreground);
  border-color: transparent;
}

.log-loading {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.log-skeleton {
  height: 48px;
  border-radius: 8px;
  background: linear-gradient(90deg, var(--card-muted) 25%, var(--secondary) 50%, var(--card-muted) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }

  100% {
    background-position: -200% 0;
  }
}

.log-error,
.log-empty {
  text-align: center;
  padding: 32px 0;
  color: var(--muted);
}

.log-table-container {
  max-height: 400px;
  overflow-y: auto;
  overflow-x: hidden;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--card-muted);
}

.log-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
  table-layout: fixed;
}

.log-table thead {
  position: sticky;
  top: 0;
  z-index: 1;
}

.log-table th {
  background: var(--secondary);
  padding: 12px 12px;
  text-align: left;
  font-weight: 600;
  color: var(--foreground);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.log-table td {
  padding: 12px 12px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.log-table tbody tr:last-child td {
  border-bottom: none;
}

.header-cell {
  display: flex;
  align-items: center;
  min-height: 20px;
}

.header-cell-status {
  justify-content: center;
}

.log-row-clickable {
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.log-row-clickable:hover {
  background-color: var(--secondary);
}

.log-row-success {
  background: linear-gradient(0deg, rgba(74, 222, 128, 0.04), rgba(74, 222, 128, 0.04));
}

.log-row-running {
  background: linear-gradient(0deg, rgba(251, 191, 36, 0.04), rgba(251, 191, 36, 0.04));
}

.log-row-failed {
  background-color: var(--danger-soft);
}

.log-row-failed:hover {
  background:
    linear-gradient(0deg, var(--danger-soft), var(--danger-soft)),
    var(--secondary);
}

.col-task {
  width: auto;
  color: var(--foreground);
}

.task-name {
  display: block;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 0.9rem;
}

.col-status {
  width: 116px;
  text-align: center;
}

.status-cell {
  padding-right: 12px;
  padding-left: 12px;
}

.status-chip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  font-size: 0.78rem;
  font-weight: 600;
}

.status-success {
  color: var(--success);
}

.status-failed {
  color: var(--danger);
}

.status-running {
  color: var(--warning);
}

.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: currentColor;
  animation: none;
}

.status-running .status-dot {
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.5;
  }
}

.log-table-container::-webkit-scrollbar {
  width: 6px;
}

.log-table-container::-webkit-scrollbar-track {
  background: var(--card-muted);
  border-radius: 3px;
}

.log-table-container::-webkit-scrollbar-thumb {
  background: var(--border-strong);
  border-radius: 3px;
}

.log-pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.page-btn {
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--card-muted);
  font-size: 0.875rem;
  color: var(--muted-foreground);
  cursor: pointer;
  transition: all 0.15s ease;
}

.page-btn:hover:not(:disabled) {
  border-color: var(--border-strong);
  color: var(--foreground);
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  font-size: 0.875rem;
  color: var(--muted);
}

.log-detail-content {
  max-height: none;
  overflow: visible;
}

.detail-header {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}

.detail-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.meta-label {
  font-size: 0.75rem;
  color: var(--muted);
  text-transform: uppercase;
}

.meta-value {
  font-size: 0.875rem;
  color: var(--foreground);
  font-weight: 500;
}

.detail-section {
  margin-bottom: 16px;
}

.detail-section.empty {
  text-align: center;
  color: var(--muted);
  padding: 24px;
}

.section-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--foreground);
  margin: 0 0 8px;
}

.section-title.error-title {
  color: var(--danger);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.live-log-hint {
  font-size: 0.75rem;
  color: var(--warning);
}

.copy-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--card-muted);
  font-size: 0.75rem;
  color: var(--muted-foreground);
  cursor: pointer;
  transition: all 0.15s ease;
}

.copy-btn:hover {
  border-color: var(--border-strong);
  color: var(--foreground);
  background: var(--secondary);
}

.log-output,
.log-error-detail {
  background: var(--card-muted);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px;
  font-family: 'SF Mono', Monaco, Inconsolata, 'Fira Code', monospace;
  font-size: 0.8rem;
  line-height: 1.5;
  color: var(--muted-foreground);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: none;
  overflow: visible;
  margin: 0;
}

.log-error-detail {
  background: var(--danger-soft);
  color: var(--danger);
  border-color: var(--danger-border);
}

.log-output-live {
  border-color: color-mix(in srgb, var(--warning) 40%, var(--border));
  min-height: 240px;
  max-height: 420px;
  overflow: auto;
}

.running-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 0;
}

.running-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.running-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 32px;
}

.running-indicator {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--warning);
  font-size: 0.875rem;
}

@media (max-width: 640px) {
  .running-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .running-actions {
    justify-content: space-between;
  }
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--warning);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
