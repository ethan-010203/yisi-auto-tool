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
  placeholder: {
    type: String,
    default: '点击选择文件...',
  },
  accept: {
    type: String,
    default: undefined, // e.g., '.xlsx,.xls' or 'image/*'
  },
  webkitdirectory: {
    type: Boolean,
    default: false, // true for folder selection
  },
})

const emit = defineEmits(['update:modelValue'])

const handleClick = () => {
  const input = document.createElement('input')
  input.type = 'file'
  
  if (props.accept) {
    input.accept = props.accept
  }
  
  if (props.webkitdirectory) {
    input.webkitdirectory = true
    input.directory = true
  }
  
  input.style.display = 'none'
  document.body.appendChild(input)
  
  input.addEventListener('change', (e) => {
    const files = e.target.files
    if (files && files.length > 0) {
      if (props.webkitdirectory) {
        // For folder, get the folder path from the first file's path
        const path = files[0].path || files[0].name
        emit('update:modelValue', path)
      } else {
        // For single file
        const path = files[0].path || files[0].name
        emit('update:modelValue', path)
      }
    }
    document.body.removeChild(input)
  })
  
  input.addEventListener('cancel', () => {
    document.body.removeChild(input)
  })
  
  input.click()
}
</script>

<template>
  <div class="ui-file-input" @click="handleClick">
    <input
      :id="id"
      type="text"
      readonly
      :value="modelValue"
      :placeholder="placeholder"
      class="ui-file-input-field"
    />
    <button type="button" class="ui-file-input-button">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
        <polyline points="14 2 14 8 20 8"/>
      </svg>
      浏览
    </button>
  </div>
</template>

<style scoped>
.ui-file-input {
  display: flex;
  gap: 8px;
  cursor: pointer;
}

.ui-file-input-field {
  flex: 1;
  height: 40px;
  padding: 0 12px;
  border-radius: 10px;
  border: 1px solid #e4e4e7;
  background: white;
  font-size: 0.875rem;
  color: #18181b;
  cursor: pointer;
  outline: none;
  transition: all 0.15s ease;
}

.ui-file-input-field::placeholder {
  color: #a1a1aa;
}

.ui-file-input:hover .ui-file-input-field {
  border-color: #d4d4d8;
}

.ui-file-input-field:focus {
  border-color: #18181b;
  box-shadow: 0 0 0 2px rgba(24, 24, 27, 0.1);
}

.ui-file-input-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 40px;
  padding: 0 14px;
  border-radius: 10px;
  border: 1px solid #d4d4d8;
  background: white;
  font-size: 0.88rem;
  font-weight: 500;
  color: #18181b;
  cursor: pointer;
  transition: all 0.18s ease;
  flex-shrink: 0;
}

.ui-file-input-button:hover {
  background: #f4f4f5;
  border-color: #18181b;
}

.ui-file-input-button svg {
  width: 14px;
  height: 14px;
}
</style>
