import { computed, ref, unref } from 'vue'
import { getToolConfig, getToolTemplateUrl, listMailFolders, saveConfig } from '../api/index'

export function createDefaultConfigData() {
  return {
    folderPath: '',
    folderDisplay: '',
    excelPath: '',
    listExcelPath: '',
    listExcelDisplay: '',
    excelFilePath: '',
    excelFileDisplay: '',
    excelFolderPath: '',
    excelFolderDisplay: '',
    reportYear: '',
    reportMonthGerman: '',
    email: '',
    authCode: '',
    maxEmails: 50,
    subjectKeyword: '注销成功',
    selectedFolder: '',
  }
}

export function sanitizePathInput(value) {
  const raw = String(value ?? '').trim()
  if (raw.length >= 2) {
    const firstChar = raw[0]
    const lastChar = raw[raw.length - 1]
    if ((firstChar === '"' && lastChar === '"') || (firstChar === "'" && lastChar === "'")) {
      return raw.slice(1, -1).trim()
    }
  }
  return raw
}

export function normalizeInvoiceRecognizerConfig(config) {
  const folderPath = sanitizePathInput(config.folderPath || '')
  const listExcelPath = sanitizePathInput(config.listExcelPath || config.excelPath || '')

  return {
    ...config,
    folderPath,
    folderDisplay: folderPath,
    excelPath: listExcelPath,
    listExcelPath,
    listExcelDisplay: listExcelPath,
  }
}

export function normalizeEarDeclarationFetcherConfig(config) {
  const excelFilePath = sanitizePathInput(config.excelFilePath || config.excelFolderPath || '')
  const reportYear = String(config.reportYear || '').trim()
  const reportMonthGerman = String(config.reportMonthGerman || '').trim()

  return {
    ...config,
    excelFilePath,
    excelFileDisplay: excelFilePath,
    excelFolderPath: excelFilePath,
    excelFolderDisplay: excelFilePath,
    reportYear,
    reportMonthGerman,
  }
}

export function validateInvoiceRecognizerManualPathsOrThrow(config) {
  const folderPath = sanitizePathInput(config.folderPath || '')
  const excelPath = sanitizePathInput(config.listExcelPath || config.excelPath || '')

  if (!folderPath || !excelPath) {
    throw new Error('请先手动填写单据文件夹和 Excel 的真实路径。')
  }
  if (!excelPath.toLowerCase().endsWith('.xlsx')) {
    throw new Error('Excel 清单必须是 .xlsx 文件。')
  }
}

export function validateEarDeclarationFetcherConfigOrThrow(config) {
  const excelFilePath = sanitizePathInput(config.excelFilePath || config.excelFolderPath || '')
  const reportYear = String(config.reportYear || '').trim()
  const reportMonthGerman = String(config.reportMonthGerman || '').trim()

  if (!excelFilePath) {
    throw new Error('请先填写申报数据 Excel 文件路径。')
  }
  const lowerPath = excelFilePath.toLowerCase()
  if (!lowerPath.endsWith('.xlsx') && !lowerPath.endsWith('.xlsm')) {
    throw new Error('申报数据 Excel 必须是 .xlsx 或 .xlsm 文件。')
  }
  if (!reportYear) {
    throw new Error('请先填写检测年份。')
  }
  if (!reportMonthGerman) {
    throw new Error('请先填写德语月份。')
  }
}

export function useToolConfig({
  departments,
  activeDepartmentCode,
  getToolKey,
  pushToast,
  onConfigSaved,
}) {
  const configDialogOpen = ref(false)
  const toolConfigCache = ref({})
  const configData = ref(createDefaultConfigData())
  const currentConfigTool = ref({ department: '', toolId: '' })
  const mailFolders = ref([])
  const loadingFolders = ref(false)
  const mailFoldersError = ref('')
  const loadingToolConfig = ref(false)
  const savingToolConfig = ref(false)
  const departmentList = computed(() => unref(departments) || [])

  const folderOptions = computed(() => {
    if (mailFolders.value.length === 0) {
      return [{ value: '', label: '请先输入邮箱和授权码', disabled: true }]
    }

    const options = mailFolders.value.map(folder => {
      const label = folder.type === 'inbox' ? '收件箱' :
                    folder.type === 'sent' ? '已发送' :
                    folder.type === 'drafts' ? '草稿箱' :
                    folder.type === 'trash' ? '垃圾箱' :
                    folder.display
      return {
        value: folder.encoded,
        label,
        type: folder.type,
        badge: null,
      }
    })

    return options.sort((a, b) => {
      const aIsSystem = a.type !== 'other'
      const bIsSystem = b.type !== 'other'

      if (aIsSystem && !bIsSystem) return -1
      if (!aIsSystem && bIsSystem) return 1

      return a.label.localeCompare(b.label, 'zh-CN')
    })
  })

  const configDialogTitle = computed(() => {
    if (currentConfigTool.value.toolId === 'citeo_email_extractor') {
      return '邮箱配置'
    }
    return '英德单据识别配置'
  })

  const configDialogDescription = computed(() => {
    if (currentConfigTool.value.toolId === 'citeo_email_extractor') {
      return '163邮箱已配置，用于 IMAP 连接提取邮件。'
    }
    return ''
  })

  const activeConfigDialogTitle = computed(() => {
    if (currentConfigTool.value.toolId === 'ear_declaration_data_fetcher') {
      return 'EAR 抓取配置'
    }
    return configDialogTitle.value
  })

  const activeConfigDialogDescription = computed(() => {
    if (currentConfigTool.value.toolId === 'ear_declaration_data_fetcher') {
      return '填写申报数据 Excel 文件路径，并配置检测年份和德语月份；EAR 官网账号和密码将从表格列中读取。'
    }
    return configDialogDescription.value
  })

  function getCachedToolConfig(departmentCode, toolId) {
    return toolConfigCache.value[getToolKey(departmentCode, toolId)] || null
  }

  function hasSavedToolConfig(departmentCode, toolId) {
    const config = getCachedToolConfig(departmentCode, toolId)
    if (!config) {
      return false
    }

    if (toolId === 'invoice_recognizer') {
      const folderPath = sanitizePathInput(config.folderPath || config.folderDisplay || '')
      const excelPath = sanitizePathInput(config.listExcelPath || config.excelPath || config.listExcelDisplay || '')
      return Boolean(folderPath && excelPath)
    }

    if (toolId === 'ear_declaration_data_fetcher') {
      const excelFilePath = sanitizePathInput(config.excelFilePath || config.excelFolderPath || '')
      const reportYear = String(config.reportYear || '').trim()
      const reportMonthGerman = String(config.reportMonthGerman || '').trim()
      return Boolean(excelFilePath && reportYear && reportMonthGerman)
    }

    if (toolId === 'citeo_email_extractor') {
      const selectedFolder = String(config.selectedFolder || '').trim()
      return Boolean(selectedFolder)
    }

    return true
  }

  function cacheToolConfig(departmentCode, toolId, config) {
    toolConfigCache.value = {
      ...toolConfigCache.value,
      [getToolKey(departmentCode, toolId)]: {
        ...config,
      },
    }
  }

  function updateInvoiceFolderPath(value) {
    const normalizedValue = sanitizePathInput(value)
    configData.value.folderPath = normalizedValue
    configData.value.folderDisplay = normalizedValue
  }

  function updateInvoiceExcelPath(value) {
    const normalizedValue = sanitizePathInput(value)
    configData.value.listExcelPath = normalizedValue
    configData.value.excelPath = normalizedValue
    configData.value.listExcelDisplay = normalizedValue
  }

  function updateEarExcelFilePath(value) {
    const normalizedValue = sanitizePathInput(value)
    configData.value.excelFilePath = normalizedValue
    configData.value.excelFileDisplay = normalizedValue
    configData.value.excelFolderPath = normalizedValue
    configData.value.excelFolderDisplay = normalizedValue
  }

  function updateConfigField({ key, value }) {
    configData.value[key] = value
  }

  function downloadEarTemplate() {
    try {
      const url = getToolTemplateUrl('BUE1', 'ear_declaration_data_fetcher')
      window.open(url, '_blank', 'noopener')
    } catch (error) {
      pushToast({
        type: 'error',
        title: '模板下载失败',
        message: error?.message || '无法下载 EAR 模板，请稍后重试。',
      })
    }
  }

  async function loadToolConfig(department, toolId) {
    try {
      const response = await getToolConfig(department, toolId)
      const cfg = response?.success && response.config ? response.config : {}
      configData.value = {
        ...createDefaultConfigData(),
        folderPath: cfg.folderPath || '',
        folderDisplay: cfg.folderDisplay || cfg.folderPath || '',
        excelPath: cfg.excelPath || cfg.listExcelPath || '',
        listExcelPath: cfg.listExcelPath || '',
        listExcelDisplay: cfg.listExcelDisplay || cfg.listExcelPath || cfg.excelPath || '',
        excelFilePath: cfg.excelFilePath || cfg.excelFolderPath || '',
        excelFileDisplay: cfg.excelFileDisplay || cfg.excelFilePath || cfg.excelFolderDisplay || cfg.excelFolderPath || '',
        excelFolderPath: cfg.excelFilePath || cfg.excelFolderPath || '',
        excelFolderDisplay: cfg.excelFileDisplay || cfg.excelFilePath || cfg.excelFolderDisplay || cfg.excelFolderPath || '',
        reportYear: cfg.reportYear || '',
        reportMonthGerman: cfg.reportMonthGerman || '',
        email: cfg.email || '',
        authCode: cfg.authCode || '',
        maxEmails: cfg.maxEmails || 50,
        subjectKeyword: cfg.subjectKeyword || '注销成功',
        selectedFolder: cfg.selectedFolder || '',
      }
      cacheToolConfig(department, toolId, configData.value)
    } catch (error) {
      console.error('Failed to load config:', error)
    }
  }

  async function preloadDepartmentToolConfigs(departmentCode) {
    const department = departmentList.value.find((item) => item.code === departmentCode)
    if (!department) {
      return
    }

    const configurableTools = department.tools.filter((tool) => tool.configurable)
    await Promise.allSettled(configurableTools.map(async (tool) => {
      const response = await getToolConfig(departmentCode, tool.id)
      const config = response?.success && response.config ? response.config : {}

      if (tool.id === 'invoice_recognizer') {
        cacheToolConfig(departmentCode, tool.id, normalizeInvoiceRecognizerConfig(config))
        return
      }

      if (tool.id === 'ear_declaration_data_fetcher') {
        cacheToolConfig(departmentCode, tool.id, normalizeEarDeclarationFetcherConfig(config))
        return
      }

      cacheToolConfig(departmentCode, tool.id, {
        ...createDefaultConfigData(),
        ...config,
      })
    }))
  }

  async function openConfigDialog(tool) {
    currentConfigTool.value = {
      department: activeDepartmentCode.value,
      toolId: tool.id,
    }
    configData.value = createDefaultConfigData()
    mailFolders.value = []
    mailFoldersError.value = ''
    configDialogOpen.value = true
    loadingToolConfig.value = true

    try {
      await loadToolConfig(activeDepartmentCode.value, tool.id)

      if (tool.id === 'citeo_email_extractor' && configData.value.email && configData.value.authCode) {
        await loadMailFolders()
      }
    } finally {
      loadingToolConfig.value = false
    }
  }

  async function loadMailFolders() {
    const { email, authCode } = configData.value
    if (!email || !authCode) {
      return
    }

    loadingFolders.value = true
    mailFoldersError.value = ''
    try {
      const result = await listMailFolders({ email, authCode })
      if (result?.success && result.folders && result.folders.length > 0) {
        mailFolders.value = result.folders
        mailFoldersError.value = ''
        const inbox = result.folders.find(f => f.type === 'inbox')
        if (inbox && !configData.value.selectedFolder) {
          configData.value.selectedFolder = inbox.encoded
        }
      } else {
        mailFolders.value = []
        mailFoldersError.value = result?.error || '无法获取文件夹列表，请检查邮箱账号、授权码和 IMAP 设置。'
      }
    } catch (error) {
      mailFolders.value = []
      mailFoldersError.value = '网络请求失败，请检查网络连接。'
    } finally {
      loadingFolders.value = false
    }
  }

  async function saveConfiguration() {
    if (loadingToolConfig.value) {
      return
    }

    const { department, toolId } = currentConfigTool.value
    const targetDept = department || 'CONSULT'
    const targetTool = toolId || 'invoice_recognizer'
    savingToolConfig.value = true

    try {
      let payload = { ...configData.value }

      if (targetTool === 'invoice_recognizer') {
        payload = normalizeInvoiceRecognizerConfig(configData.value)
      } else if (targetTool === 'ear_declaration_data_fetcher') {
        payload = normalizeEarDeclarationFetcherConfig(configData.value)
      }

      if (targetTool === 'invoice_recognizer') {
        validateInvoiceRecognizerManualPathsOrThrow(payload)
      } else if (targetTool === 'ear_declaration_data_fetcher') {
        validateEarDeclarationFetcherConfigOrThrow(payload)
      }

      const response = await saveConfig(targetDept, targetTool, payload)
      if (!response?.success) {
        throw new Error(response?.error || '保存失败')
      }

      configData.value = payload
      cacheToolConfig(targetDept, targetTool, payload)
      configDialogOpen.value = false
      pushToast({
        type: 'success',
        title: '配置已保存',
      })
      await onConfigSaved?.({ department: targetDept, toolId: targetTool })
    } catch (error) {
      console.error('Failed to save config:', error)
      pushToast({
        type: 'error',
        title: '保存失败',
        message: error.message || '请检查配置内容后重试。',
      })
    } finally {
      savingToolConfig.value = false
    }
  }

  return {
    configDialogOpen,
    toolConfigCache,
    configData,
    currentConfigTool,
    mailFolders,
    loadingFolders,
    mailFoldersError,
    loadingToolConfig,
    savingToolConfig,
    folderOptions,
    activeConfigDialogTitle,
    activeConfigDialogDescription,
    getCachedToolConfig,
    hasSavedToolConfig,
    cacheToolConfig,
    updateInvoiceFolderPath,
    updateInvoiceExcelPath,
    updateEarExcelFilePath,
    updateConfigField,
    downloadEarTemplate,
    loadToolConfig,
    preloadDepartmentToolConfigs,
    openConfigDialog,
    loadMailFolders,
    saveConfiguration,
  }
}
