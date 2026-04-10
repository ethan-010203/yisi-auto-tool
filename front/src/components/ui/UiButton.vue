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
})
</script>

<template>
  <button :type="props.type" class="ui-button" :class="`ui-button--${props.variant}`">
    <slot />
  </button>
</template>
