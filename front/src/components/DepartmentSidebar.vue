<script setup>
import UiBadge from './ui/UiBadge.vue'
import UiButton from './ui/UiButton.vue'
import UiCard from './ui/UiCard.vue'

defineProps({
  departments: {
    type: Array,
    required: true,
  },
  activeWorkspaceView: {
    type: String,
    required: true,
  },
  activeDepartmentCode: {
    type: String,
    required: true,
  },
  activeDepartment: {
    type: Object,
    required: true,
  },
  activeToolCount: {
    type: Number,
    required: true,
  },
  connectionStatus: {
    type: Object,
    required: true,
  },
  statusBadgeVariant: {
    type: String,
    required: true,
  },
})

defineEmits(['show-dashboard', 'select-department'])
</script>

<template>
  <UiCard class="mobile-workspace-card">
    <div class="mobile-workspace-head">
      <div class="mobile-workspace-copy">
        <UiBadge variant="secondary">移动工作台</UiBadge>
        <strong>{{ activeWorkspaceView === 'dashboard' ? '全局仪表盘' : activeDepartment.name }}</strong>
        <small>{{ connectionStatus.label }} · {{ activeWorkspaceView === 'dashboard' ? '查看全部任务' : `${activeToolCount} 个可用工具` }}</small>
      </div>
      <UiButton :variant="activeWorkspaceView === 'dashboard' ? 'default' : 'outline'" size="sm" @click="$emit('show-dashboard')">
        仪表盘
      </UiButton>
    </div>

    <nav class="mobile-department-scroll" aria-label="移动端部门切换">
      <UiButton
        v-for="department in departments"
        :key="department.code"
        :variant="activeWorkspaceView === 'department' && department.code === activeDepartmentCode ? 'default' : 'outline'"
        size="sm"
        @click="$emit('select-department', department.code)"
      >
        {{ department.name }}
      </UiButton>
    </nav>
  </UiCard>

  <aside class="workspace-sidebar">
    <UiCard class="department-sidebar">
      <div class="sidebar-head">
        <div class="sidebar-copy">
          <UiBadge variant="secondary">部门导航</UiBadge>
          <h2>工作区切换</h2>
          <p>左侧切换部门，右侧直接处理当前工作区的任务与配置。</p>
        </div>
        <div class="sidebar-status">
          <UiBadge :variant="statusBadgeVariant">{{ connectionStatus.label }}</UiBadge>
          <small>{{ connectionStatus.detail }}</small>
        </div>
      </div>

      <nav class="sidebar-department-list" aria-label="部门切换">
        <button
          type="button"
          class="sidebar-department-button sidebar-dashboard-button"
          :class="{ active: activeWorkspaceView === 'dashboard' }"
          :aria-current="activeWorkspaceView === 'dashboard' ? 'page' : undefined"
          @click="$emit('show-dashboard')"
        >
          <div class="sidebar-department-top">
            <div class="sidebar-department-title">
              <strong>仪表盘</strong>
              <span>全局运行任务</span>
            </div>
          </div>
        </button>

        <button
          v-for="department in departments"
          :key="department.code"
          type="button"
          class="sidebar-department-button sidebar-department-button--compact"
          :class="{ active: activeWorkspaceView === 'department' && department.code === activeDepartmentCode }"
          :aria-current="activeWorkspaceView === 'department' && department.code === activeDepartmentCode ? 'page' : undefined"
          @click="$emit('select-department', department.code)"
        >
          <strong>{{ department.name }}</strong>
          <span>{{ department.tools.length }} 个工具</span>
        </button>
      </nav>
    </UiCard>
  </aside>
</template>

<style scoped>
.mobile-workspace-card {
  display: none;
}

.workspace-sidebar {
  max-height: calc(100vh - 3rem);
  min-height: 0;
  overflow: hidden;
  align-self: start;
}

.department-sidebar {
  display: grid;
  gap: 1rem;
  max-height: 100%;
  overflow-y: auto;
}

.sidebar-head,
.sidebar-copy,
.sidebar-status,
.sidebar-department-list {
  display: grid;
  gap: 0.75rem;
}

.sidebar-copy h2 {
  margin: 0;
  font-size: 1.2rem;
  line-height: 1.15;
  letter-spacing: -0.03em;
}

.sidebar-status {
  padding: 0.875rem;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--card-muted);
}

.sidebar-status small,
.sidebar-copy p {
  color: var(--muted-foreground);
  line-height: 1.6;
}

.sidebar-department-button {
  display: grid;
  gap: 0.65rem;
  width: 100%;
  padding: 0.95rem 1rem;
  text-align: left;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--card);
  color: inherit;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    background 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
}

.sidebar-department-button--compact {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  min-height: 44px;
  padding: 0.62rem 0.75rem;
  border-radius: 12px;
}

.sidebar-department-button--compact strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.92rem;
  line-height: 1.2;
}

.sidebar-department-button--compact span {
  flex-shrink: 0;
  color: var(--muted-foreground);
  font-size: 0.78rem;
  font-weight: 600;
}

.sidebar-department-button:hover {
  border-color: var(--border-strong);
  background: var(--card-muted);
  box-shadow: 0 0 0 3px var(--ring);
  transform: translateY(-1px);
}

.sidebar-department-button.active {
  border-color: var(--accent);
  background: var(--card-muted);
  box-shadow: 0 0 0 3px var(--ring);
}

.sidebar-department-top {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  align-items: flex-start;
}

.sidebar-department-title {
  display: grid;
  gap: 0.25rem;
}

.sidebar-department-title strong {
  font-size: 1rem;
  line-height: 1.2;
}

.sidebar-department-title span {
  color: var(--muted-foreground);
  line-height: 1.55;
}

@media (max-width: 980px) {
  .mobile-workspace-card {
    position: sticky;
    top: 0.65rem;
    z-index: 10;
    display: grid;
    gap: 0.85rem;
    width: 100%;
    padding: 0.9rem;
    backdrop-filter: blur(16px);
  }

  .mobile-workspace-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .mobile-workspace-copy {
    display: grid;
    gap: 0.35rem;
    min-width: 0;
  }

  .mobile-workspace-copy strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 1.05rem;
    line-height: 1.2;
    letter-spacing: -0.03em;
  }

  .mobile-workspace-copy small {
    color: var(--muted-foreground);
    line-height: 1.4;
  }

  .mobile-department-scroll {
    display: flex;
    gap: 0.5rem;
    overflow-x: auto;
    padding-bottom: 0.15rem;
    scrollbar-width: none;
    scroll-snap-type: x proximity;
  }

  .mobile-department-scroll::-webkit-scrollbar {
    display: none;
  }

  .mobile-department-scroll :deep(.ui-button) {
    flex: 0 0 auto;
    scroll-snap-align: start;
  }

  .workspace-sidebar {
    display: none;
  }
}

@media (max-width: 560px) {
  .mobile-workspace-card {
    top: 0.5rem;
    border-radius: 18px;
  }

  .mobile-workspace-head {
    align-items: stretch;
  }

  .mobile-workspace-head > :deep(.ui-button) {
    min-width: 5rem;
  }
}
</style>
