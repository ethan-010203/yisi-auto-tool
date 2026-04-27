<script setup>
import UiBadge from './ui/UiBadge.vue'
import UiButton from './ui/UiButton.vue'
import UiCard from './ui/UiCard.vue'

defineProps({
  tools: {
    type: Array,
    required: true,
  },
  activeDepartmentCode: {
    type: String,
    required: true,
  },
  toolRequiresNetworkPath: {
    type: Function,
    required: true,
  },
  isToolPending: {
    type: Function,
    required: true,
  },
  isToolBusy: {
    type: Function,
    required: true,
  },
})

defineEmits(['configure', 'preview', 'preview-warm', 'primary-action'])
</script>

<template>
  <div class="tool-grid">
    <UiCard
      v-for="tool in tools"
      :key="tool.id"
      class="tool-card"
      :tone="tool.setupState.key === 'ready' ? 'default' : 'muted'"
    >
      <div class="tool-card-head">
        <div class="tool-card-headline">
          <h3>{{ tool.name }}</h3>
        </div>
      </div>
      <div class="tool-card-body">
        <p>{{ tool.description }}</p>
        <p class="tool-card-state-copy">{{ tool.setupState.description }}</p>
        <div class="tool-card-meta">
          <UiBadge v-if="tool.configurable" variant="outline">支持配置</UiBadge>
          <UiBadge
            v-if="toolRequiresNetworkPath(activeDepartmentCode, tool.id)"
            variant="warning"
          >
            依赖共享目录
          </UiBadge>
          <UiBadge v-if="tool.previewable" variant="outline">支持预览</UiBadge>
        </div>
      </div>
      <div class="tool-card-foot">
        <div class="tool-card-actions">
          <UiButton
            v-if="tool.configurable"
            variant="outline"
            :disabled="isToolPending(activeDepartmentCode, tool.id)"
            @click="$emit('configure', tool)"
          >
            配置
          </UiButton>
          <UiButton
            v-if="tool.previewable"
            variant="outline"
            @mouseenter="$emit('preview-warm', tool)"
            @focus="$emit('preview-warm', tool)"
            @click="$emit('preview', tool)"
          >
            预览
          </UiButton>
        </div>
        <UiButton
          :variant="tool.setupState.key === 'ready' ? 'default' : 'outline'"
          :loading="tool.setupState.primaryAction === 'run' && isToolBusy(activeDepartmentCode, tool.id)"
          :disabled="tool.setupState.primaryDisabled || isToolPending(activeDepartmentCode, tool.id)"
          @click="$emit('primary-action', tool)"
        >
          {{ tool.setupState.primaryLabel }}
        </UiButton>
      </div>
    </UiCard>
  </div>
</template>

<style scoped>
.tool-card {
  gap: 0.9rem;
}

.tool-card-headline {
  display: grid;
  gap: 0.55rem;
}

.tool-card-headline h3 {
  font-size: 1.08rem;
  line-height: 1.2;
  letter-spacing: -0.03em;
}

.tool-card-state-copy {
  color: var(--foreground);
  font-size: 0.88rem;
  line-height: 1.55;
}

@media (max-width: 980px) {
  .tool-card-actions {
    display: grid;
    grid-template-columns: 1fr;
    width: 100%;
  }

  .tool-card-actions :deep(.ui-button),
  .tool-card-foot > :deep(.ui-button) {
    width: 100%;
  }

  .tool-grid {
    grid-template-columns: 1fr;
    grid-auto-rows: auto;
    gap: 0.75rem;
  }

  .tool-card {
    min-height: 0;
    padding: 1rem;
  }

  .tool-card-foot {
    display: grid;
    gap: 0.75rem;
  }
}
</style>
