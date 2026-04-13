<script setup>
import { computed, onMounted, ref, watch, onUnmounted } from 'vue'
import { getDepartmentLogs, getToolLogs, clearDepartmentLogs, terminateExecution } from '../api/index'
import UiCard from './ui/UiCard.vue'
import UiBadge from './ui/UiBadge.vue'
import UiDialog from './ui/UiDialog.vue'
import UiButton from './ui/UiButton.vue'
import UiInput from './ui/UiInput.vue'
import UiToastStack from './ui/UiToastStack.vue'
import { departments } from '../data/departments'

const logs = ref([])
const loading = ref(false)
const error = ref(null)
const currentPage = ref(1)
const itemsPerPage = 10  // 每页显示10条
const searchQuery = ref('')
const statusFilter = ref('all') // all, success, failed, running

// 轮询定时器
const pollInterval = ref(null)
const POLL_DELAY = 2000 // 2秒轮询一次

// 计算是否有运行中的任务
const hasRunningTasks = computed(() => {
  return logs.value.some(log => log.status === 'running')
})

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

const emit = defineEmits(['task-complete'])

// 筛选后的日志
const filteredLogs = computed(() => {
  let result = logs.value
  
  // 状态筛选
  if (statusFilter.value !== 'all') {
    result = result.filter(log => log.status === statusFilter.value)
  }
  
  // 搜索筛选
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(log => {
      const toolName = getToolName(log.tool).toLowerCase()
      const output = (log.output || '').toLowerCase()
      const errorMsg = (log.error || '').toLowerCase()
      return toolName.includes(query) || output.includes(query) || errorMsg.includes(query)
    })
  }
  
  return result
})

const totalPages = computed(() => Math.ceil(filteredLogs.value.length / itemsPerPage))

const displayedLogs = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage
  const end = start + itemsPerPage
  return filteredLogs.value.slice(start, end)
})

// 获取工具中文名
function getToolName(toolId) {
  const dept = departments.find(d => d.code === props.department)
  if (!dept) return toolId
  const tool = dept.tools.find(t => t.id === toolId)
  return tool?.name || toolId
}

async function loadLogs() {
  if (!props.department) {
    logs.value = []
    return
  }

  try {
    let response
    if (props.tool) {
      // 获取指定工具的日志
      response = await getToolLogs(props.department, props.tool, props.limit)
    } else {
      // 获取整个部门的日志
      response = await getDepartmentLogs(props.department, props.limit)
    }

    if (response?.success) {
      logs.value = response.logs || []
      // 调试：检查运行中任务的时间戳
      const runningLogs = logs.value.filter(log => log.status === 'running')
      if (runningLogs.length > 0) {
        console.log('Running tasks:', runningLogs.map(log => ({ id: log.id, timestamp: log.timestamp, tool: log.tool })))
      }
      // 如果详情弹窗打开，同步更新selectedLog
      if (detailDialogOpen.value && selectedLog.value) {
        const updatedLog = logs.value.find(log => log.id === selectedLog.value.id)
        if (updatedLog) {
          selectedLog.value = updatedLog
        }
      }
    } else {
      error.value = response?.error || '加载失败'
    }
  } catch (err) {
    error.value = err.message || '网络错误'
  }
}

// 启动轮询
function startPolling() {
  stopPolling()
  pollInterval.value = setInterval(() => {
    loadLogs()
  }, POLL_DELAY)
}

// 停止轮询
function stopPolling() {
  if (pollInterval.value) {
    clearInterval(pollInterval.value)
    pollInterval.value = null
  }
}

// 打开终止确认弹窗
function openTerminateDialog(logId) {
  terminateTargetId.value = logId
  terminateDialogOpen.value = true
}

// 关闭终止确认弹窗
function closeTerminateDialog() {
  terminateDialogOpen.value = false
  terminateTargetId.value = null
  terminateLoading.value = false
}

// 确认终止执行
async function confirmTerminate() {
  if (!terminateTargetId.value) return
  
  terminateLoading.value = true
  try {
    const response = await terminateExecution(terminateTargetId.value)
    if (response?.success) {
      // 关闭弹窗和详情弹窗
      closeTerminateDialog()
      detailDialogOpen.value = false
      selectedLog.value = null
      // 刷新日志
      setTimeout(() => {
        loadLogs()
      }, 100)
      // 显示成功提示
      pushToast({
        type: 'success',
        title: '任务已终止',
        message: '任务已成功终止并记录到日志中。',
        duration: 3000,
      })
    } else {
      pushToast({
        type: 'error',
        title: '终止失败',
        message: response?.error || '无法终止任务',
        duration: 4000,
      })
    }
  } catch (err) {
    pushToast({
      type: 'error',
      title: '网络错误',
      message: err.message || '请检查网络连接',
      duration: 4000,
    })
  } finally {
    terminateLoading.value = false
  }
}

// 跟踪之前的运行状态，用于检测任务完成
const hadRunningTasks = ref(false)

// 监听部门变化，自动重新加载
watch(() => props.department, () => {
  currentPage.value = 1
  // 重置运行状态跟踪
  hadRunningTasks.value = false
  loadLogs().then(() => {
    // 加载完成后初始化运行状态
    hadRunningTasks.value = hasRunningTasks.value
    // 如果有运行中的任务，启动轮询
    if (hasRunningTasks.value) {
      startPolling()
    }
  })
}, { immediate: true })

// 监听日志变化，自动启停轮询
watch(() => logs.value, (newLogs) => {
  const hasRunning = newLogs.some(log => log.status === 'running')
  if (hasRunning && !pollInterval.value) {
    startPolling()
  } else if (!hasRunning && pollInterval.value) {
    stopPolling()
  }
  // 检测任务从运行中变为完成
  if (hadRunningTasks.value && !hasRunning) {
    emit('task-complete')
  }
  hadRunningTasks.value = hasRunning
}, { deep: true })

// 组件卸载时停止轮询
onUnmounted(() => {
  stopPolling()
})

function prevPage() {
  if (currentPage.value > 1) {
    currentPage.value--
  }
}

function nextPage() {
  if (currentPage.value < totalPages.value) {
    currentPage.value++
  }
}

function formatTime(timestamp) {
  if (!timestamp) {
    return '-'
  }
  const date = new Date(timestamp)
  if (isNaN(date.getTime())) {
    return '-'
  }
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).replace(/\//g, '-')
}

function formatEndTime(timestamp, duration) {
  if (!timestamp || duration === undefined || duration === null) {
    return '-'
  }
  const date = new Date(timestamp)
  if (isNaN(date.getTime())) {
    return '-'
  }
  // 计算结束时间：开始时间 + 时长（秒）
  const endDate = new Date(date.getTime() + duration * 1000)
  return endDate.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).replace(/\//g, '-')
}

const clearDialogOpen = ref(false)
const clearLoading = ref(false)
const detailDialogOpen = ref(false)
const selectedLog = ref(null)
const terminateDialogOpen = ref(false)
const terminateLoading = ref(false)
const terminateTargetId = ref(null)

// Toast 通知系统
const toasts = ref([])
const toastTimers = new Map()

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

function openClearDialog() {
  clearDialogOpen.value = true
}

function openDetailDialog(log) {
  selectedLog.value = log
  detailDialogOpen.value = true
}

function closeDetailDialog() {
  detailDialogOpen.value = false
  selectedLog.value = null
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
  // 导出日志为CSV
  const csvContent = [
    ['执行时间', '任务名称', '状态', '执行时长', '输出'],
    ...filteredLogs.value.map(log => [
      formatTime(log.timestamp),
      getToolName(log.tool),
      log.status === 'success' ? '成功' : '失败',
      formatDuration(log.duration),
      (log.output || '').replace(/\n/g, ' ')
    ])
  ].map(row => row.map(cell => `"${cell}"`).join(',')).join('\n')
  
  const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `执行记录_${props.department}_${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
}

function formatDuration(seconds) {
  if (seconds === undefined || seconds === null) {
    return '-'
  }
  if (seconds < 1) {
    return `${(seconds * 1000).toFixed(0)}ms`
  }
  return `${seconds.toFixed(1)}s`
}

const copySuccess = ref(false)

async function copyError() {
  const text = selectedLog.value?.error || selectedLog.value?.output
  if (!text) {
    console.warn('copyError: no text to copy')
    return
  }

  console.log('Attempting to copy text length:', text.length)

  try {
    const blob = new Blob([text], { type: 'text/plain' })
    const clipboardItem = new ClipboardItem({ 'text/plain': blob })
    await navigator.clipboard.write([clipboardItem])
    copySuccess.value = true
    setTimeout(() => copySuccess.value = false, 1500)
    console.log('ClipboardItem API succeeded')
  } catch (err) {
    console.warn('ClipboardItem API failed:', err)

    try {
      await navigator.clipboard.writeText(text)
      copySuccess.value = true
      setTimeout(() => copySuccess.value = false, 1500)
      console.log('writeText API succeeded')
    } catch (err2) {
      console.warn('writeText API failed:', err2)
      console.log('Trying fallback copy...')
      const ok = fallbackCopy(text)
      if (ok) {
        copySuccess.value = true
        setTimeout(() => copySuccess.value = false, 1500)
      } else {
        pushToast({
          type: 'error',
          title: '复制失败',
          message: '请手动复制内容',
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

  const range = document.createRange()
  range.selectNode(el)

  const selection = window.getSelection()
  selection.removeAllRanges()
  selection.addRange(range)

  el.select()
  el.setSelectionRange(0, el.value.length)

  let ok = false
  try {
    ok = document.execCommand('copy')
    console.log('execCommand result:', ok)
  } catch (e) {
    console.error('execCommand copy failed:', e)
  }

  selection.removeAllRanges()
  document.body.removeChild(el)

  return ok
}

onMounted(() => {
  if (props.department) {
    loadLogs().then(() => {
      // 初始化运行状态跟踪
      hadRunningTasks.value = hasRunningTasks.value
    })
  }
})

defineExpose({
  refresh: loadLogs,
  onTaskStarted: () => {
    // 任务启动后立即标记为运行中，确保能检测到后续完成状态
    hadRunningTasks.value = true
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
        <span class="log-count" v-if="filteredLogs.length > 0">共 {{ filteredLogs.length }} 条记录</span>
      </div>
      <div class="log-actions">
        <UiButton
          variant="outline"
          :loading="clearLoading"
          :disabled="loading || logs.length === 0"
          @click="openClearDialog"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 6px;">
            <path d="M3 6h18"/>
            <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>
            <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
          </svg>
          清空
        </UiButton>
        <UiButton
          variant="outline"
          :loading="loading"
          @click="loadLogs"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 6px;">
            <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
            <path d="M3 3v5h5"/>
            <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
            <path d="M16 16h5v5"/>
          </svg>
          刷新
        </UiButton>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="log-filter-bar">
      <UiInput
        v-model="searchQuery"
        placeholder="搜索任务名称或日志内容..."
        class="search-input"
      />
      <div class="status-filter">
        <button
          v-for="option in [{value: 'all', label: '全部'}, {value: 'running', label: '运行中'}, {value: 'success', label: '成功'}, {value: 'failed', label: '失败'}]"
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
      <div class="log-skeleton" v-for="i in 5" :key="i" />
    </div>

    <div v-else-if="error" class="log-error">
      <p>{{ error }}</p>
    </div>

    <div v-else-if="displayedLogs.length === 0" class="log-empty">
      <p>{{ searchQuery || statusFilter !== 'all' ? '没有找到匹配的记录' : (hasRunningTasks ? '任务运行中...' : '暂无执行记录') }}</p>
    </div>

    <!-- 表格布局 -->
    <div v-else class="log-table-container">
      <table class="log-table">
        <thead>
          <tr>
            <th class="col-time">时间</th>
            <th class="col-task">任务</th>
            <th class="col-status">结果</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="log in displayedLogs"
            :key="log.id"
            class="log-row-clickable"
            :class="{
              'log-row-success': log.status === 'success',
              'log-row-running': log.status === 'running',
              'log-row-failed': log.status !== 'success' && log.status !== 'running'
            }"
            @click="openDetailDialog(log)"
          >
            <td class="col-time">{{ formatTime(log.timestamp) }}</td>
            <td class="col-task">
              <span class="task-name" :title="getToolName(log.tool)">{{ getToolName(log.tool) }}</span>
            </td>
            <td class="col-status">
              <span :class="['status-chip', log.status === 'success' ? 'status-success' : log.status === 'running' ? 'status-running' : 'status-failed']">
                <span class="status-dot"></span>
                <span>{{ log.status === 'success' ? '成功' : log.status === 'running' ? '运行中' : '失败' }}</span>
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="totalPages > 1" class="log-pagination">
      <button 
        class="page-btn" 
        :disabled="currentPage === 1"
        @click="prevPage"
      >
        ← 上一页
      </button>
      <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
      <button 
        class="page-btn" 
        :disabled="currentPage === totalPages"
        @click="nextPage"
      >
        下一页 →
      </button>
    </div>

    <!-- 清空确认弹窗 -->
    <UiDialog
      v-model:open="clearDialogOpen"
      title="清空执行记录"
      description="确定要清空当前所有的执行记录吗？此操作无法撤销。"
    >
      <template #footer>
        <UiButton variant="outline" :disabled="clearLoading" @click="clearDialogOpen = false">取消</UiButton>
        <UiButton :loading="clearLoading" @click="confirmClearLogs">确认清空</UiButton>
      </template>
    </UiDialog>

    <!-- 详情弹窗 -->
    <UiDialog
      v-model:open="detailDialogOpen"
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
              <UiBadge :variant="selectedLog.status === 'success' ? 'success' : selectedLog.status === 'running' ? 'warning' : 'danger'">
                {{ selectedLog.status === 'success' ? '成功' : selectedLog.status === 'running' ? '运行中' : '失败' }}
              </UiBadge>
            </div>
            <div class="meta-item">
              <span class="meta-label">执行时长</span>
              <span class="meta-value">{{ formatDuration(selectedLog.duration) }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">结束时间</span>
              <span class="meta-value">{{ selectedLog.status === 'running' ? '-' : formatEndTime(selectedLog.timestamp, selectedLog.duration) }}</span>
            </div>
          </div>
        </div>
        
        <div v-if="selectedLog.status === 'running'" class="detail-section running-section">
          <div class="running-indicator">
            <div class="spinner"></div>
            <span>任务正在执行中...</span>
          </div>
          <UiButton variant="outline" size="sm" @click="openTerminateDialog(selectedLog.id)">
            终止执行
          </UiButton>
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
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
              <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              {{ copySuccess ? '已复制' : '复制' }}
            </button>
          </div>
          <pre class="log-error-detail">{{ selectedLog.error }}</pre>
        </div>

        <div v-if="selectedLog.status !== 'running' && !selectedLog.output && !selectedLog.error" class="detail-section empty">
          <p>没有输出日志</p>
        </div>
      </div>
      <template #footer>
        <UiButton variant="outline" @click="closeDetailDialog">关闭</UiButton>
      </template>
    </UiDialog>

    <!-- 终止确认弹窗 -->
    <UiDialog
      v-model:open="terminateDialogOpen"
      title="确认终止任务"
      description="确定要终止当前正在运行的任务吗？此操作无法撤销。"
    >
      <template #footer>
        <UiButton variant="outline" :disabled="terminateLoading" @click="closeTerminateDialog">取消</UiButton>
        <UiButton :loading="terminateLoading" @click="confirmTerminate">确认终止</UiButton>
      </template>
    </UiDialog>
  </UiCard>

  <UiToastStack :toasts="toasts" @dismiss="dismissToast" />
</template>

<style scoped>
.log-panel {
  padding: 20px;
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

.log-refresh {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--card-muted);
  font-size: 0.875rem;
  color: var(--muted-foreground);
  cursor: pointer;
  transition: all 0.15s ease;
}

.log-refresh:hover {
  border-color: var(--border-strong);
  color: var(--foreground);
}

.log-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.log-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.log-actions .ui-button {
  flex-shrink: 0;
}

.log-refresh svg {
  transition: transform 0.3s ease;
}

.log-refresh:not(:disabled):hover svg {
  transform: rotate(180deg);
}

/* 筛选栏 */
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
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.log-error,
.log-empty {
  text-align: center;
  padding: 32px 0;
  color: var(--muted);
}

/* 表格样式 */
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
  min-width: 0;
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
  padding: 12px 8px;
  text-align: left;
  font-weight: 600;
  color: var(--foreground);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.log-table td {
  padding: 12px 8px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.log-table tbody tr:last-child td {
  border-bottom: none;
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

.col-time {
  width: 135px;
  min-width: 135px;
  max-width: 135px;
  color: var(--muted);
  white-space: nowrap;
  font-size: 0.8rem;
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
  font-size: 0.8rem;
}

.col-status {
  width: 84px;
  min-width: 84px;
  max-width: 84px;
  text-align: right;
}

.status-chip {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  font-size: 0.75rem;
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
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.terminate-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-left: 6px;
  padding: 2px;
  border: none;
  background: transparent;
  color: var(--danger);
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.15s ease;
}

.terminate-btn:hover {
  background: var(--danger-soft);
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

/* 详情弹窗样式 */
.log-detail-content {
  max-height: 500px;
  overflow-y: auto;
}

.detail-header {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}

.detail-meta {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
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
  margin: 0 0 8px 0;
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
  max-height: 300px;
  overflow-y: auto;
  margin: 0;
}

.log-error-detail {
  background: var(--danger-soft);
  color: var(--danger);
  border-color: var(--danger-border);
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

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--warning);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
