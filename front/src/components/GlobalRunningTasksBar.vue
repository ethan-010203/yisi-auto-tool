<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { getExecutionLogs, getGlobalEventsUrl } from '../api/index'
import { departments } from '../data/departments'
import UiBadge from './ui/UiBadge.vue'
import UiButton from './ui/UiButton.vue'
import UiCard from './ui/UiCard.vue'

const props = defineProps({
  limit: {
    type: Number,
    default: 50,
  },
  displayLimit: {
    type: Number,
    default: 6,
  },
})

const emit = defineEmits(['focus-department'])

const logs = ref([])
const loading = ref(false)
const error = ref('')
const streamConnected = ref(false)
const reconnectTimer = ref(null)
const liveRefreshTimer = ref(null)
const liveRefreshInFlight = ref(false)
const pendingExecutions = ref({})
let eventSource = null

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

function getStatusVariant(status) {
  if (status === 'running') return 'warning'
  if (status === 'queued') return 'secondary'
  if (status === 'cancelling') return 'warning'
  return 'outline'
}

function getDepartmentMeta(code) {
  return departments.find((item) => item.code === code)
}

function getToolName(departmentCode, toolId) {
  const department = getDepartmentMeta(departmentCode)
  const tool = department?.tools?.find((item) => item.id === toolId)
  return tool?.name || toolId
}

function syncSnapshot(snapshot) {
  logs.value = Array.isArray(snapshot?.logs) ? snapshot.logs : []
  error.value = ''
  streamConnected.value = true
  prunePendingExecutions(logs.value)
  if (shouldKeepLiveRefresh()) {
    scheduleLiveRefresh()
  } else {
    stopLiveRefresh()
  }
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
  return activeLogs.value.length > 0 || hasPendingExecutions()
}

function scheduleLiveRefresh(delay = 1200) {
  if (liveRefreshTimer.value || !shouldKeepLiveRefresh()) {
    return
  }

  liveRefreshTimer.value = setTimeout(async () => {
    liveRefreshTimer.value = null

    if (liveRefreshInFlight.value) {
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

async function loadLogs(options = {}) {
  const { silent = false } = options
  if (!silent) {
    loading.value = true
  }
  try {
    const response = await getExecutionLogs(props.limit)
    if (!response?.success) {
      throw new Error(response?.error || '无法获取全局任务列表')
    }
    logs.value = response.logs || []
    error.value = ''
  } catch (err) {
    error.value = err.message || '请求失败'
  } finally {
    prunePendingExecutions(logs.value)
    if (shouldKeepLiveRefresh()) {
      scheduleLiveRefresh()
    } else {
      stopLiveRefresh()
    }
    if (!silent) {
      loading.value = false
    }
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
  if (reconnectTimer.value) return
  reconnectTimer.value = setTimeout(() => {
    reconnectTimer.value = null
    connectEventStream()
  }, 2500)
}

function connectEventStream() {
  closeEventStream()

  const url = getGlobalEventsUrl(props.limit)
  eventSource = new EventSource(url)

  eventSource.addEventListener('snapshot', (event) => {
    try {
      syncSnapshot(JSON.parse(event.data))
    } catch (parseError) {
      console.error('Failed to parse global SSE payload:', parseError)
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

function focusDepartment(departmentCode) {
  emit('focus-department', departmentCode)
}

const activeLogs = computed(() => logs.value.filter((log) => isActiveStatus(log.status)))

const visibleActiveLogs = computed(() => activeLogs.value.slice(0, props.displayLimit))

const hiddenActiveCount = computed(() => Math.max(0, activeLogs.value.length - visibleActiveLogs.value.length))

const runningCount = computed(() => activeLogs.value.filter((log) => log.status === 'running').length)
const queuedCount = computed(() => activeLogs.value.filter((log) => log.status === 'queued').length)
const cancellingCount = computed(() => activeLogs.value.filter((log) => log.status === 'cancelling').length)
const activeDepartmentCount = computed(() => new Set(activeLogs.value.map((log) => log.department)).size)

onMounted(async () => {
  await loadLogs()
  connectEventStream()
})

onUnmounted(() => {
  closeEventStream()
  stopLiveRefresh()
})

defineExpose({
  refresh: loadLogs,
  onTaskStarted: (payload) => {
    startTaskLiveRefresh(payload)
  },
})
</script>

<template>
  <UiCard class="global-running-bar">
    <div class="global-running-head">
      <div class="global-running-copy">
        <div class="global-running-title-row">
          <UiBadge variant="secondary">全局任务</UiBadge>
          <UiBadge :variant="streamConnected ? 'success' : 'warning'">
            {{ streamConnected ? '实时已连接' : '实时重连中' }}
          </UiBadge>
        </div>
        <h2>全局运行任务</h2>
      </div>

      <div class="global-running-actions">
        <div class="global-running-stats">
          <div class="global-stat">
            <span>运行</span>
            <strong>{{ runningCount }}</strong>
          </div>
          <div class="global-stat">
            <span>排队</span>
            <strong>{{ queuedCount }}</strong>
          </div>
          <div class="global-stat">
            <span>部门</span>
            <strong>{{ activeDepartmentCount }}</strong>
          </div>
        </div>
        <UiButton variant="outline" :loading="loading" @click="loadLogs">
          刷新
        </UiButton>
      </div>
    </div>

    <div v-if="error" class="global-running-error">
      {{ error }}
    </div>

    <div v-else-if="visibleActiveLogs.length === 0" class="global-running-empty">
      当前没有排队或运行中的任务。
      <span v-if="cancellingCount > 0">仍有 {{ cancellingCount }} 个任务处于取消中。</span>
    </div>

    <div v-else class="global-task-list">
      <button
        v-for="log in visibleActiveLogs"
        :key="log.id"
        type="button"
        class="global-task-card"
        @click="focusDepartment(log.department)"
      >
        <div class="global-task-top">
          <UiBadge variant="outline">{{ log.department }}</UiBadge>
          <UiBadge :variant="getStatusVariant(log.status)">
            {{ getStatusLabel(log.status) }}
          </UiBadge>
        </div>
        <strong>{{ getToolName(log.department, log.tool) }}</strong>
        <div class="global-task-meta">
          <span v-if="log.queuePosition">队列 #{{ log.queuePosition }}</span>
          <span v-else-if="log.duration !== undefined && log.duration !== null">已执行 {{ Number(log.duration).toFixed(1) }}s</span>
          <span v-else>等待 worker 处理</span>
        </div>
      </button>

      <div v-if="hiddenActiveCount > 0" class="global-task-more">
        还有 {{ hiddenActiveCount }} 个运行任务未展开显示
      </div>
    </div>
  </UiCard>
</template>

<style scoped>
.global-running-bar {
  display: grid;
  gap: 0.85rem;
  margin-top: 20px;
}

.global-running-head {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
  flex-wrap: wrap;
}

.global-running-copy {
  display: grid;
  gap: 0.4rem;
}

.global-running-title-row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
}

.global-running-copy h2 {
  margin: 0;
  font-size: 1rem;
  line-height: 1.15;
  letter-spacing: -0.03em;
}

.global-running-actions {
  display: flex;
  gap: 0.75rem;
  align-items: stretch;
  flex-wrap: wrap;
}

.global-running-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.5rem;
}

.global-stat {
  min-width: 92px;
  padding: 0.7rem 0.8rem;
  border: 1px solid var(--border);
  border-radius: 0.95rem;
  background: var(--card-muted);
}

.global-stat span {
  display: block;
  color: var(--muted);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.global-stat strong {
  display: block;
  margin-top: 0.4rem;
  font-size: 1.15rem;
}

.global-running-error,
.global-running-empty {
  padding: 1rem;
  border-radius: 1rem;
  border: 1px dashed var(--border);
  color: var(--muted-foreground);
  text-align: center;
}

.global-running-error {
  color: var(--danger);
  border-color: var(--danger-border);
  background: var(--danger-soft);
}

.global-task-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 0.65rem;
}

.global-task-card {
  display: grid;
  gap: 0.5rem;
  padding: 0.85rem 0.95rem;
  border: 1px solid var(--border);
  border-radius: 1rem;
  background: var(--card-muted);
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
}

.global-task-card:hover {
  border-color: var(--border-strong);
  box-shadow: 0 0 0 3px var(--ring);
  transform: translateY(-1px);
}

.global-task-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.global-task-card strong {
  font-size: 0.92rem;
  line-height: 1.45;
}

.global-task-meta {
  color: var(--muted-foreground);
  font-size: 0.82rem;
  font-weight: 500;
}

.global-task-more {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100%;
  padding: 0.95rem 1rem;
  border: 1px dashed var(--border);
  border-radius: 1rem;
  color: var(--muted-foreground);
  background: var(--card-muted);
}

@media (max-width: 900px) {
  .global-running-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .global-running-stats {
    grid-template-columns: 1fr;
  }

  .global-running-actions {
    width: 100%;
  }

  .global-running-actions .ui-button {
    width: 100%;
  }
}
</style>
