import { ref } from 'vue'

export function useExecutionEvents({ getToolKey, logPanel, globalRunningBar }) {
  const activeToolIdsByDepartment = ref({})
  const pendingToolKeys = ref({})

  function getDepartmentActiveToolIds(departmentCode) {
    return activeToolIdsByDepartment.value[departmentCode] || []
  }

  function getDepartmentActiveToolCount(departmentCode) {
    return getDepartmentActiveToolIds(departmentCode).length
  }

  function isToolActive(departmentCode, toolId) {
    return getDepartmentActiveToolIds(departmentCode).includes(toolId)
  }

  function setToolPendingState(departmentCode, toolId, pending) {
    const key = getToolKey(departmentCode, toolId)
    if (pending) {
      pendingToolKeys.value = {
        ...pendingToolKeys.value,
        [key]: true,
      }
      return
    }

    const nextState = { ...pendingToolKeys.value }
    delete nextState[key]
    pendingToolKeys.value = nextState
  }

  function isToolPending(departmentCode, toolId) {
    return Boolean(pendingToolKeys.value[getToolKey(departmentCode, toolId)])
  }

  function isToolBusy(departmentCode, toolId) {
    return isToolPending(departmentCode, toolId) || isToolActive(departmentCode, toolId)
  }

  function setDepartmentActiveTools(departmentCode, toolIds) {
    activeToolIdsByDepartment.value = {
      ...activeToolIdsByDepartment.value,
      [departmentCode]: [...toolIds],
    }
  }

  function addActiveTool(departmentCode, toolId) {
    const current = new Set(getDepartmentActiveToolIds(departmentCode))
    current.add(toolId)
    setDepartmentActiveTools(departmentCode, [...current])
  }

  function handleActiveToolsChange(payload) {
    if (!payload?.department) {
      return
    }

    setDepartmentActiveTools(payload.department, payload.toolIds || [])
  }

  async function refreshExecutionViews() {
    await Promise.allSettled([
      logPanel.value?.refresh?.({ silent: true }),
      globalRunningBar.value?.refresh?.({ silent: true }),
    ])
  }

  function notifyTaskStarted({ toolId, logId, status }) {
    globalRunningBar.value?.onTaskStarted({ toolId, logId, status })
    logPanel.value?.onTaskStarted({ toolId, logId, status })
  }

  function refreshGlobalRunningBar(options = { silent: true }) {
    return globalRunningBar.value?.refresh?.(options)
  }

  return {
    activeToolIdsByDepartment,
    pendingToolKeys,
    getDepartmentActiveToolIds,
    getDepartmentActiveToolCount,
    isToolActive,
    setToolPendingState,
    isToolPending,
    isToolBusy,
    setDepartmentActiveTools,
    addActiveTool,
    handleActiveToolsChange,
    refreshExecutionViews,
    notifyTaskStarted,
    refreshGlobalRunningBar,
  }
}
