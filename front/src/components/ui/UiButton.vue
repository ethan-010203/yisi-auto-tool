<script setup>
const props = defineProps({
  variant: {
    type: String,
    default: 'default',
  },
  type: {
    type: String,
    default: 'button',
  },
  loading: {
    type: Boolean,
    default: false,
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  size: {
    type: String,
    default: 'default',
  },
})
</script>

<template>
  <button
    :type="props.type"
    class="ui-button"
    :class="[`ui-button--${props.variant}`, `ui-button--size-${props.size}`, { 'ui-button--loading': props.loading }]"
    :disabled="props.loading || props.disabled"
  >
    <span v-if="props.loading" class="ui-button-spinner">
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
    </span>
    <slot />
  </button>
</template>
