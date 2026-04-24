<script setup>
import { computed } from 'vue'
import { DialogClose, DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle, DialogTrigger } from 'radix-vue'

const props = defineProps({
  open: {
    type: Boolean,
    default: false,
  },
  keepMounted: {
    type: Boolean,
    default: false,
  },
  size: {
    type: String,
    default: 'default',
  },
  title: {
    type: String,
    default: '',
  },
  description: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:open'])

const openValue = computed({
  get: () => props.open,
  set: (value) => emit('update:open', value),
})

const handleInteractOutside = (event) => {
  // 阻止点击遮罩层关闭弹窗
  event.preventDefault()
}
</script>

<template>
  <DialogRoot v-model:open="openValue" modal>
    <DialogTrigger v-if="$slots.trigger" as-child>
      <slot name="trigger" />
    </DialogTrigger>
    <DialogPortal>
      <DialogOverlay class="ui-dialog-overlay" />
      <DialogContent
        class="ui-dialog-content"
        :class="`ui-dialog-content--${props.size}`"
        @interact-outside="handleInteractOutside"
      >
        <div class="ui-dialog-header">
          <DialogTitle class="ui-dialog-title">{{ title }}</DialogTitle>
          <DialogDescription v-if="description" class="ui-dialog-description">
            {{ description }}
          </DialogDescription>
        </div>
        <div class="ui-dialog-body">
          <slot />
        </div>
        <div v-if="$slots.footer" class="ui-dialog-footer">
          <slot name="footer" />
        </div>
        <DialogClose class="ui-dialog-close-btn" aria-label="Close">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m18 6-12 12"/><path d="m6 6 12 12"/></svg>
        </DialogClose>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.ui-dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  animation: overlayShow 150ms cubic-bezier(0.16, 1, 0.3, 1);
  z-index: 40;
}

.ui-dialog-content {
  position: fixed;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: min(calc(100vw - 32px), 425px);
  max-height: 85vh;
  background: var(--card);
  border-radius: 16px;
  border: 1px solid var(--border);
  box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1);
  padding: 24px;
  animation: contentShow 150ms cubic-bezier(0.16, 1, 0.3, 1);
  z-index: 50;
  overflow-y: auto;
  overflow-x: hidden;
}

.ui-dialog-content--wide {
  width: min(calc(100vw - 32px), 880px);
}

.ui-dialog-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 20px;
}

.ui-dialog-title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.02em;
  color: var(--foreground);
}

.ui-dialog-description {
  margin: 0;
  font-size: 0.875rem;
  color: var(--muted);
  line-height: 1.4;
}

.ui-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ui-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.ui-dialog-close-btn {
  position: absolute;
  top: 16px;
  right: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  transition: all 0.15s ease;
  padding: 0;
}

.ui-dialog-close-btn:hover {
  background: var(--secondary);
  color: var(--foreground);
}

@keyframes overlayShow {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes contentShow {
  from {
    opacity: 0;
    transform: translate(-50%, -48%) scale(0.96);
  }
  to {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }
}
</style>
