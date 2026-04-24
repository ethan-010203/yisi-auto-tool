<script setup>
defineProps({
  toasts: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['dismiss'])
</script>

<template>
  <div class="ui-toast-stack" aria-live="polite" aria-atomic="true">
    <article
      v-for="toast in toasts"
      :key="toast.id"
      class="ui-toast"
      :class="`ui-toast--${toast.type || 'info'}`"
    >
      <div class="ui-toast-copy">
        <strong>{{ toast.title }}</strong>
        <p v-if="toast.message">{{ toast.message }}</p>
      </div>
      <button type="button" class="ui-toast-close" @click="emit('dismiss', toast.id)">
        关闭
      </button>
    </article>
  </div>
</template>

<style scoped>
.ui-toast-stack {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 80;
  display: grid;
  gap: 12px;
  width: min(360px, calc(100vw - 24px));
}

.ui-toast {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: var(--card);
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(14px);
}

.ui-toast-copy {
  display: grid;
  gap: 4px;
}

.ui-toast-copy strong {
  color: var(--foreground);
}

.ui-toast-copy p {
  margin: 0;
  color: var(--muted-foreground);
  font-size: 0.9rem;
  line-height: 1.45;
}

.ui-toast-close {
  border: 0;
  padding: 0;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 0.82rem;
  white-space: nowrap;
}

.ui-toast--success {
  border-color: var(--success-border);
  background: linear-gradient(0deg, var(--success-soft), var(--success-soft)), var(--card);
}

.ui-toast--warning {
  border-color: var(--warning-border);
  background: linear-gradient(0deg, var(--warning-soft), var(--warning-soft)), var(--card);
}

.ui-toast--error {
  border-color: var(--danger-border);
  background: linear-gradient(0deg, var(--danger-soft), var(--danger-soft)), var(--card);
}

</style>
