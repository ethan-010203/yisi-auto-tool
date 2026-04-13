<script setup>
const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  id: {
    type: String,
    default: undefined,
  },
  type: {
    type: String,
    default: 'text',
  },
  placeholder: {
    type: String,
    default: '',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  readonly: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue', 'click'])

const handleInput = (e) => {
  emit('update:modelValue', e.target.value)
}

const handleClick = (e) => {
  emit('click', e)
}
</script>

<template>
  <input
    :id="id"
    :type="type"
    :value="modelValue"
    :placeholder="placeholder"
    :disabled="disabled"
    :readonly="readonly"
    class="ui-input"
    @input="handleInput"
    @click="handleClick"
  />
</template>

<style scoped>
.ui-input {
  display: flex;
  width: 100%;
  height: 40px;
  padding: 0 12px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--card);
  font-size: 0.875rem;
  line-height: 1.25rem;
  color: var(--foreground);
  transition: all 0.15s ease;
  outline: none;
}

.ui-input::placeholder {
  color: var(--muted);
}

.ui-input:hover {
  border-color: var(--border-strong);
}

.ui-input:focus {
  border-color: var(--foreground);
  box-shadow: 0 0 0 2px var(--ring);
}

.ui-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: var(--card-muted);
}

.ui-input[readonly] {
  cursor: pointer;
  background: var(--card-muted);
}
</style>
