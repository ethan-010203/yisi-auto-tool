const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })

  const payload = await response.json().catch(() => null)

  if (!response.ok) {
    const error = new Error(payload?.error || payload?.message || `Request failed with status ${response.status}`)
    error.status = response.status
    error.payload = payload
    throw error
  }

  return payload
}

export function getData(signal) {
  return requestJson(`${API_BASE_URL}/health`, { signal })
}

export function runDepartmentTool(department, tool, signal) {
  return requestJson(`${API_BASE_URL}/departments/${department}/tools/${tool}/run`, {
    method: 'POST',
    signal,
  })
}

export function saveConfig(department, tool, config, signal) {
  return requestJson(`${API_BASE_URL}/departments/${department}/tools/${tool}/config`, {
    method: 'POST',
    body: JSON.stringify(config),
    signal,
  })
}

export function getToolConfig(department, tool, signal) {
  return requestJson(`${API_BASE_URL}/departments/${department}/tools/${tool}/config`, {
    signal,
  })
}

export function getToolPreview(department, tool, signal) {
  return requestJson(`${API_BASE_URL}/departments/${department}/tools/${tool}/preview`, {
    signal,
  })
}

export function getExecutionLogs(limit = 20, department = null, signal) {
  const deptParam = department ? `&department=${department}` : ''
  return requestJson(`${API_BASE_URL}/logs?limit=${limit}${deptParam}`, { signal })
}

export function getDepartmentLogs(department, limit = 20, signal) {
  return requestJson(`${API_BASE_URL}/departments/${department}/logs?limit=${limit}`, { signal })
}

export function getToolLogs(department, tool, limit = 10, signal) {
  return requestJson(`${API_BASE_URL}/departments/${department}/tools/${tool}/logs?limit=${limit}`, { signal })
}

export function clearDepartmentLogs(department, signal) {
  return requestJson(`${API_BASE_URL}/departments/${department}/logs`, {
    method: 'DELETE',
    signal,
  })
}

// 部门配置 API
export function getDepartmentConfig(department, signal) {
  return requestJson(`${API_BASE_URL}/departments/${department}/config`, {
    signal,
  })
}

export function saveDepartmentConfig(department, config, signal) {
  return requestJson(`${API_BASE_URL}/departments/${department}/config`, {
    method: 'POST',
    body: JSON.stringify(config),
    signal,
  })
}

export function testNetworkPath(path, signal) {
  return requestJson(`${API_BASE_URL}/test-network-path`, {
    method: 'POST',
    body: JSON.stringify({ path }),
    signal,
  })
}

export function terminateExecution(logId, signal) {
  return requestJson(`${API_BASE_URL}/executions/${logId}/terminate`, {
    method: 'POST',
    signal,
  })
}
