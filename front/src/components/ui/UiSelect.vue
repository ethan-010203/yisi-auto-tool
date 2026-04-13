<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  id: {
    type: String,
    default: undefined,
  },
  placeholder: {
    type: String,
    default: '请选择...',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  options: {
    type: Array,
    default: () => [],
  },
  searchable: {
    type: Boolean,
    default: true,
  },
})

const emit = defineEmits(['update:modelValue'])

const isOpen = ref(false)
const searchQuery = ref('')
const triggerRef = ref(null)
const contentRef = ref(null)
const dropdownStyle = ref({})

const selectedOption = computed(() => {
  return props.options.find(opt => opt.value === props.modelValue)
})

const filteredOptions = computed(() => {
  if (!searchQuery.value) return props.options
  const query = searchQuery.value.toLowerCase()
  return props.options.filter(opt => 
    opt.label.toLowerCase().includes(query)
  )
})

const displayLabel = computed(() => {
  return selectedOption.value?.label || props.placeholder
})

// 计算下拉框位置
const updatePosition = () => {
  if (!triggerRef.value || !isOpen.value) return
  
  const rect = triggerRef.value.getBoundingClientRect()
  const viewportHeight = window.innerHeight
  const dropdownHeight = 300 // 最大高度
  
  // 检查下方空间是否足够
  const spaceBelow = viewportHeight - rect.bottom
  const showAbove = spaceBelow < dropdownHeight && rect.top > dropdownHeight
  
  if (showAbove) {
    // 向上展开
    dropdownStyle.value = {
      position: 'fixed',
      left: `${rect.left}px`,
      bottom: `${viewportHeight - rect.top + 4}px`,
      width: `${rect.width}px`,
      zIndex: 9999,
    }
  } else {
    // 向下展开
    dropdownStyle.value = {
      position: 'fixed',
      left: `${rect.left}px`,
      top: `${rect.bottom + 4}px`,
      width: `${rect.width}px`,
      zIndex: 9999,
    }
  }
}

const toggleOpen = () => {
  if (props.disabled) return
  isOpen.value = !isOpen.value
  if (isOpen.value) {
    searchQuery.value = ''
    nextTick(() => {
      updatePosition()
      // 自动聚焦搜索框
      const searchInput = contentRef.value?.querySelector('.search-input')
      if (searchInput) searchInput.focus()
    })
  }
}

const selectOption = (option, event) => {
  if (option.disabled) return
  event.stopPropagation()
  emit('update:modelValue', option.value)
  isOpen.value = false
  searchQuery.value = ''
}

const closeOnClickOutside = (e) => {
  const contentEl = contentRef.value
  if (triggerRef.value && !triggerRef.value.contains(e.target) && 
      (!contentEl || !contentEl.contains(e.target))) {
    isOpen.value = false
  }
}

// 监听窗口变化更新位置
const handleResize = () => {
  if (isOpen.value) {
    updatePosition()
  }
}

onMounted(() => {
  document.addEventListener('click', closeOnClickOutside)
  window.addEventListener('resize', handleResize)
  window.addEventListener('scroll', handleResize, true)
})

onUnmounted(() => {
  document.removeEventListener('click', closeOnClickOutside)
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('scroll', handleResize, true)
})

// 监听打开状态，更新位置
watch(isOpen, (open) => {
  if (open) {
    nextTick(updatePosition)
  }
})
</script>

<template>
  <div ref="triggerRef" class="ui-select-wrapper">
    <button
      type="button"
      class="ui-select-trigger"
      :disabled="disabled"
      @click="toggleOpen"
    >
      <span class="select-label" :class="{ 'placeholder': !selectedOption }">
        {{ displayLabel }}
      </span>
      <svg
        class="select-icon"
        :class="{ 'open': isOpen }"
        xmlns="http://www.w3.org/2000/svg"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="m6 9 6 6 6-6"/>
      </svg>
    </button>

    <Teleport to="body">
      <div v-if="isOpen" ref="contentRef" class="ui-select-content" :style="dropdownStyle">
        <div v-if="searchable" class="select-search">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="m21 21-4.3-4.3"/>
          </svg>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索文件夹..."
            class="search-input"
          />
        </div>

        <div class="select-options">
          <div
            v-for="option in filteredOptions"
            :key="option.value"
            class="select-option"
            :class="{ 
              'selected': option.value === modelValue,
              'special': option.type && option.type !== 'other',
              'disabled': option.disabled
            }"
            @click="selectOption(option, $event)"
          >
            <span class="option-label">{{ option.label }}</span>
            <span v-if="option.badge" class="option-badge">{{ option.badge }}</span>
            <svg
              v-if="option.value === modelValue"
              class="check-icon"
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M20 6 9 17l-5-5"/>
            </svg>
          </div>
          <div v-if="filteredOptions.length === 0" class="select-empty">
            无匹配选项
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.ui-select-wrapper {
  position: relative;
  width: 100%;
}

.ui-select-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  height: 40px;
  padding: 0 12px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--card);
  font-size: 0.875rem;
  line-height: 1.25rem;
  color: var(--foreground);
  transition: all 0.15s ease;
  outline: none;
  cursor: pointer;
}

.ui-select-trigger:hover {
  border-color: var(--border-strong);
}

.ui-select-trigger:focus {
  border-color: var(--foreground);
  box-shadow: 0 0 0 2px var(--ring);
}

.ui-select-trigger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: var(--card-muted);
}

.select-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
}

.select-label.placeholder {
  color: var(--muted);
}

.select-icon {
  flex-shrink: 0;
  margin-left: 8px;
  color: var(--muted);
  transition: transform 0.2s ease;
}

.select-icon.open {
  transform: rotate(180deg);
}

.ui-select-content {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  max-height: 300px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: slideIn 0.15s ease;
  pointer-events: auto;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.select-search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  color: var(--muted);
}

.search-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 0.875rem;
  color: var(--foreground);
  background: transparent;
}

.search-input::placeholder {
  color: var(--muted);
}

.select-options {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 4px;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
}

.select-options::-webkit-scrollbar {
  width: 6px;
}

.select-options::-webkit-scrollbar-track {
  background: transparent;
}

.select-options::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}

.select-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.875rem;
  color: var(--foreground);
  transition: all 0.12s ease;
  user-select: none;
  -webkit-user-select: none;
  min-height: 40px;
}

.select-option:hover:not(.disabled) {
  background: var(--secondary);
}

.select-option:active:not(.disabled) {
  background: var(--border);
}

.select-option.selected {
  background: var(--secondary);
}

.select-option.special {
  color: var(--accent);
}

.select-option.special .option-badge {
  background: var(--secondary);
  color: var(--accent);
}

.select-option.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.option-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.option-badge {
  flex-shrink: 0;
  font-size: 0.75rem;
  padding: 2px 8px;
  background: var(--secondary);
  border-radius: 4px;
  color: var(--muted);
}

.check-icon {
  flex-shrink: 0;
  color: var(--accent);
}

.select-empty {
  padding: 16px;
  text-align: center;
  font-size: 0.875rem;
  color: var(--muted);
}
</style>
