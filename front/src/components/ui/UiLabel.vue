<script setup>
const props = defineProps({
  for: {
    type: String,
    default: undefined,
  },
})
</script>

<template>
  <label :for="props.for" class="ui-label">
    <slot />
  </label>
</template>

<style scoped>
.ui-label {
  display: block;
  font-size: 0.875rem;
  font-weight: 500;
  line-height: 1;
  color: #27272a;
  margin-bottom: 8px;
}
</style>
