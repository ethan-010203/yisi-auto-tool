<script setup>
const props = defineProps({
  tone: {
    type: String,
    default: 'default',
  },
})
</script>

<template>
  <section class="ui-card" :class="`ui-card--${props.tone}`">
    <slot />
  </section>
</template>
