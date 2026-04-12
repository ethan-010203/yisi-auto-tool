<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { getDepartmentLogs, getToolLogs, clearDepartmentLogs } from '../api/index'
import UiCard from './ui/UiCard.vue'
import UiBadge from './ui/UiBadge.vue'
import UiDialog from './ui/UiDialog.vue'
import UiButton from './ui/UiButton.vue'
import { departments } from '../data/departments'

const logs = ref([])
const loading = ref(false)
const error = ref(null)
const currentPage = ref(1)
const itemsPerPage = 5  // 每页显示5条

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
    default: 20,
  },
})

const totalPages = computed(() => Math.ceil(logs.value.length / itemsPerPage))

const displayedLogs = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage
  const end = start + itemsPerPage
  return logs.value.slice(start, end)
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
  
  loading.value = true
  error.value = null
  
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
    } else {
      error.value = response?.error || '加载失败'
    }
  } catch (err) {
    error.value = err.message || '网络错误'
  } finally {
    loading.value = false
  }
}

// 监听部门变化，自动重新加载
watch(() => props.department, () => {
  currentPage.value = 1
  loadLogs()
}, { immediate: true })

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
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const clearDialogOpen = ref(false)
const clearLoading = ref(false)

function openClearDialog() {
  clearDialogOpen.value = true
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

function formatDuration(seconds) {
  if (seconds < 1) {
    return `${(seconds * 1000).toFixed(0)}ms`
  }
  return `${seconds.toFixed(1)}s`
}

onMounted(() => {
  if (props.department) {
    loadLogs()
  }
})

defineExpose({
  refresh: loadLogs,
})
</script>

<template>
  <UiCard class="log-panel">
    <div class="log-header">
      <div>
        <h3 class="log-title">执行记录</h3>
        <p class="log-subtitle">{{ props.department || '选择部门' }} 最近 {{ displayedLogs.length }} 次运行</p>
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

    <div v-if="loading" class="log-loading">
      <div class="log-skeleton" v-for="i in 3" :key="i" />
    </div>

    <div v-else-if="error" class="log-error">
      <p>{{ error }}</p>
    </div>

    <div v-else-if="displayedLogs.length === 0" class="log-empty">
      <p>暂无执行记录</p>
    </div>

    <ul v-else class="log-list">
      <li v-for="log in displayedLogs" :key="log.id" class="log-item">
        <div class="log-row">
          <span class="log-time">{{ formatTime(log.timestamp) }}</span>
          <span class="log-name">{{ getToolName(log.tool) }}</span>
          <UiBadge :variant="log.status === 'success' ? 'success' : 'warning'" class="log-status">
            {{ log.status === 'success' ? '✓' : '✗' }}
          </UiBadge>
          <span class="log-duration">{{ formatDuration(log.duration) }}</span>
        </div>
      </li>
    </ul>

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
  </UiCard>
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
}

.log-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: #18181b;
}

.log-subtitle {
  margin: 4px 0 0;
  font-size: 0.875rem;
  color: #71717a;
}

.log-refresh {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid #e4e4e7;
  border-radius: 6px;
  background: white;
  font-size: 0.875rem;
  color: #52525b;
  cursor: pointer;
  transition: all 0.15s ease;
}

.log-refresh:hover {
  border-color: #18181b;
  color: #18181b;
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

.log-loading {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.log-skeleton {
  height: 60px;
  border-radius: 8px;
  background: linear-gradient(90deg, #f4f4f5 25%, #e4e4e7 50%, #f4f4f5 75%);
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
  color: #71717a;
}

.log-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 280px;
  overflow-y: auto;
  padding-right: 4px;
}

.log-item {
  padding: 8px 0;
  border-bottom: 1px solid #e4e4e7;
}

.log-item:last-child {
  border-bottom: none;
}

.log-row {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 0.875rem;
}

.log-time {
  color: #71717a;
  font-size: 0.8rem;
  min-width: 100px;
}

.log-name {
  flex: 1;
  color: #18181b;
  font-weight: 500;
  text-transform: uppercase;
}

.log-status {
  font-size: 0.75rem;
  padding: 2px 8px;
  border-radius: 4px;
}

.log-duration {
  color: #a1a1aa;
  font-size: 0.8rem;
  min-width: 45px;
  text-align: right;
}

.log-list::-webkit-scrollbar {
  width: 4px;
}

.log-list::-webkit-scrollbar-track {
  background: #f4f4f5;
  border-radius: 2px;
}

.log-list::-webkit-scrollbar-thumb {
  background: #d4d4d8;
  border-radius: 2px;
}

.log-pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #e4e4e7;
}

.page-btn {
  padding: 6px 12px;
  border: 1px solid #e4e4e7;
  border-radius: 6px;
  background: white;
  font-size: 0.875rem;
  color: #52525b;
  cursor: pointer;
  transition: all 0.15s ease;
}

.page-btn:hover:not(:disabled) {
  border-color: #18181b;
  color: #18181b;
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  font-size: 0.875rem;
  color: #71717a;
}
</style>
