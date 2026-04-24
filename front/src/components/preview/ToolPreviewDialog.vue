<script setup>
import UiBadge from '../ui/UiBadge.vue'
import UiDialog from '../ui/UiDialog.vue'

defineProps({
  open: {
    type: Boolean,
    default: false,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  preview: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['update:open', 'refresh'])
</script>

<template>
  <UiDialog
    :open="open"
    keep-mounted
    size="wide"
    title="预览工作台"
    description="优先显示可感知的预览骨架，再异步补齐识别说明与配置状态。"
    @update:open="emit('update:open', $event)"
  >
    <section class="preview-shell">
      <div v-if="loading && !preview" class="preview-skeleton" aria-hidden="true">
        <div class="skeleton-block skeleton-block--hero" />
        <div class="skeleton-grid">
          <div v-for="item in 4" :key="item" class="skeleton-block skeleton-block--metric" />
        </div>
        <div class="skeleton-block skeleton-block--body" />
      </div>

      <template v-else-if="preview">
        <div class="preview-hero">
          <div class="preview-hero-copy">
            <p class="preview-eyebrow">{{ preview.eyebrow }}</p>
            <h3>{{ preview.title }}</h3>
            <p>{{ preview.summary }}</p>
          </div>
          <UiBadge :variant="preview.configured ? 'success' : 'warning'">
            {{ preview.configured ? '已配置' : '待配置' }}
          </UiBadge>
        </div>

        <div class="preview-metrics">
          <article v-for="metric in preview.metrics" :key="metric.label" class="preview-metric">
            <span>{{ metric.label }}</span>
            <strong>{{ metric.value }}</strong>
            <small>{{ metric.detail }}</small>
          </article>
        </div>

        <div class="preview-section">
          <div class="preview-section-head">
            <h4>执行分层</h4>
            <button type="button" class="preview-refresh" @click="emit('refresh')">
              刷新预览
            </button>
          </div>
          <ul class="preview-list">
            <li v-for="stage in preview.stages" :key="stage.name">
              <strong>{{ stage.name }}</strong>
              <span>{{ stage.description }}</span>
            </li>
          </ul>
        </div>

        <div class="preview-layout">
          <section class="preview-section">
            <h4>运行前检查</h4>
            <ul class="preview-list">
              <li v-for="item in preview.checklist" :key="item">
                <span>{{ item }}</span>
              </li>
            </ul>
          </section>

          <section class="preview-section">
            <h4>当前输入</h4>
            <ul class="preview-list">
              <li v-for="item in preview.inputs" :key="item.label">
                <strong>{{ item.label }}</strong>
                <span>{{ item.value }}</span>
              </li>
            </ul>
          </section>
        </div>
      </template>

      <div v-else class="preview-empty">
        <h3>预览暂时不可用</h3>
        <p>未能拿到可展示的预览信息，请稍后重试。</p>
      </div>
    </section>
  </UiDialog>
</template>

<style scoped>
.preview-shell {
  display: grid;
  gap: 18px;
}

.preview-hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: start;
  padding: 18px;
  border: 1px solid #e4e4e7;
  border-radius: 18px;
  background:
    radial-gradient(circle at top right, rgba(19, 78, 74, 0.12), transparent 38%),
    linear-gradient(135deg, #fffdf7 0%, #ffffff 100%);
}

.preview-hero-copy {
  display: grid;
  gap: 8px;
}

.preview-hero-copy h3,
.preview-section h4,
.preview-empty h3 {
  margin: 0;
  font-size: 1.05rem;
  line-height: 1.15;
  color: #111827;
}

.preview-hero-copy p,
.preview-empty p {
  margin: 0;
  color: #52525b;
  line-height: 1.55;
}

.preview-eyebrow {
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #0f766e;
  font-weight: 700;
}

.preview-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.preview-metric {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 16px;
  background: #fafaf9;
  border: 1px solid #e7e5e4;
}

.preview-metric span,
.preview-metric small {
  color: #71717a;
}

.preview-metric strong {
  font-size: 1rem;
  color: #18181b;
}

.preview-layout {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.preview-section {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 16px;
  border: 1px solid #e4e4e7;
  background: white;
}

.preview-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.preview-list {
  display: grid;
  gap: 10px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.preview-list li {
  display: grid;
  gap: 4px;
  padding: 12px 0;
  border-top: 1px solid #f4f4f5;
}

.preview-list li:first-child {
  border-top: 0;
  padding-top: 0;
}

.preview-list strong {
  color: #111827;
}

.preview-list span {
  color: #52525b;
}

.preview-refresh {
  padding: 0;
  border: 0;
  background: transparent;
  color: #0f766e;
  font-size: 0.88rem;
  font-weight: 600;
  cursor: pointer;
}

.preview-empty {
  display: grid;
  gap: 8px;
  padding: 12px 0 4px;
}

.preview-skeleton {
  display: grid;
  gap: 14px;
}

.skeleton-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.skeleton-block {
  border-radius: 16px;
  background:
    linear-gradient(90deg, rgba(228, 228, 231, 0.8) 25%, rgba(244, 244, 245, 1) 37%, rgba(228, 228, 231, 0.8) 63%);
  background-size: 400% 100%;
  animation: previewShimmer 1.2s ease-in-out infinite;
}

.skeleton-block--hero {
  height: 120px;
}

.skeleton-block--metric {
  height: 84px;
}

.skeleton-block--body {
  height: 220px;
}

@keyframes previewShimmer {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: 0 0;
  }
}

</style>
