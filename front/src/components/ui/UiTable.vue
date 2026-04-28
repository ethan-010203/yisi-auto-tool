<script setup>
const props = defineProps({
  tableClass: {
    type: [String, Array, Object],
    default: '',
  },
})
</script>

<template>
  <div class="ui-table-wrap">
    <table class="ui-table" :class="props.tableClass">
      <slot />
    </table>
  </div>
</template>

<style scoped>
.ui-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--card);
}

.ui-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 640px;
}

.ui-table :deep(th),
.ui-table :deep(td) {
  padding: 0.85rem 1rem;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: middle;
}

.ui-table :deep(th) {
  color: var(--muted-foreground);
  background: var(--card-muted);
  font-size: 0.8rem;
  font-weight: 700;
}

.ui-table :deep(tr:last-child td) {
  border-bottom: 0;
}
</style>
