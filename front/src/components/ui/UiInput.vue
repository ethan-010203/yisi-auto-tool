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
  border: 1px solid #e4e4e7;
  background: white;
  font-size: 0.875rem;
  line-height: 1.25rem;
  color: #18181b;
  transition: all 0.15s ease;
  outline: none;
}

.ui-input::placeholder {
  color: #a1a1aa;
}

.ui-input:hover {
  border-color: #d4d4d8;
}

.ui-input:focus {
  border-color: #18181b;
  box-shadow: 0 0 0 2px rgba(24, 24, 27, 0.1);
}

.ui-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: #fafafa;
}

.ui-input[readonly] {
  cursor: pointer;
  background: #fafafa;
}
</style>
