<script setup>
import UiBadge from './ui/UiBadge.vue'
import UiButton from './ui/UiButton.vue'
import UiCard from './ui/UiCard.vue'
import UiTable from './ui/UiTable.vue'

defineProps({
  networkConfigRows: {
    type: Array,
    required: true,
  },
  testingAllNetworkPaths: {
    type: Boolean,
    required: true,
  },
  testingNetworkPath: {
    type: Boolean,
    required: true,
  },
  testingNetworkDepartment: {
    type: String,
    required: true,
  },
  networkPathTestResult: {
    type: Object,
    default: null,
  },
})

defineEmits(['test-all', 'test-department'])
</script>

<template>
  <UiCard class="department-card dashboard-network-card">
    <div class="department-header department-header--stacked">
      <div class="department-copy">
        <UiBadge variant="outline">固定配置</UiBadge>
        <h2>各部门局域网路径</h2>
        <p>这些路径已写入系统默认配置，运行任务时会自动按部门使用对应共享目录。如需修改请联系管理员</p>
      </div>
      <UiButton variant="outline" :loading="testingAllNetworkPaths" :disabled="testingNetworkPath" @click="$emit('test-all')">
        测试所有部门连接
      </UiButton>
    </div>

    <UiTable table-class="network-config-table">
      <thead>
        <tr>
          <th>部门名称</th>
          <th>局域网地址</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in networkConfigRows" :key="item.code">
          <td>{{ item.name }}</td>
          <td><code>{{ item.networkPath }}</code></td>
          <td>
            <UiButton
              variant="outline"
              size="sm"
              :loading="testingNetworkDepartment === item.code"
              :disabled="testingAllNetworkPaths || (testingNetworkPath && testingNetworkDepartment !== item.code)"
              @click="$emit('test-department', item.code)"
            >
              测试连接
            </UiButton>
          </td>
        </tr>
      </tbody>
    </UiTable>

    <div
      v-if="networkPathTestResult"
      class="test-result"
      :class="{ success: networkPathTestResult.success, error: !networkPathTestResult.success }"
    >
      {{ networkPathTestResult.department ? `${networkPathTestResult.department}：` : '' }}{{ networkPathTestResult.message }}
    </div>
  </UiCard>
</template>

<style scoped>
:deep(.network-config-table td:first-child) {
  width: 180px;
  font-weight: 700;
}

:deep(.network-config-table td:last-child),
:deep(.network-config-table th:last-child) {
  width: 140px;
  text-align: right;
}

:deep(.network-config-table code) {
  display: block;
  min-width: 0;
  overflow-wrap: anywhere;
  padding: 0.45rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--foreground);
  background: var(--card-muted);
}

.test-result {
  margin-top: 0.75rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  font-size: 0.875rem;
  border: 1px solid transparent;
}

.test-result.success {
  background: var(--success-soft);
  border-color: var(--success-border);
  color: var(--success);
}

.test-result.error {
  background: var(--danger-soft);
  border-color: var(--danger-border);
  color: var(--danger);
}

</style>
