<script setup>
const props = defineProps({
  variant: {
    type: String,
    default: 'default',
  },
})
</script>

<template>
  <span class="ui-badge" :class="`ui-badge--${props.variant}`">
    <slot />
  </span>
</template>
