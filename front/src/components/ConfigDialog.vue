<script setup>
import UiBadge from './ui/UiBadge.vue'
import UiButton from './ui/UiButton.vue'
import UiDialog from './ui/UiDialog.vue'
import UiInput from './ui/UiInput.vue'
import UiLabel from './ui/UiLabel.vue'
import UiSelect from './ui/UiSelect.vue'

defineProps({
  open: {
    type: Boolean,
    required: true,
  },
  title: {
    type: String,
    required: true,
  },
  description: {
    type: String,
    default: '',
  },
  loadingToolConfig: {
    type: Boolean,
    required: true,
  },
  currentConfigTool: {
    type: Object,
    required: true,
  },
  configData: {
    type: Object,
    required: true,
  },
  savingToolConfig: {
    type: Boolean,
    required: true,
  },
  loadingFolders: {
    type: Boolean,
    required: true,
  },
  mailFolders: {
    type: Array,
    required: true,
  },
  mailFoldersError: {
    type: String,
    default: '',
  },
  folderOptions: {
    type: Array,
    required: true,
  },
})

const emit = defineEmits([
  'update:open',
  'update-config-field',
  'update-ear-excel-file-path',
  'update-invoice-folder-path',
  'update-invoice-excel-path',
  'download-ear-template',
  'load-mail-folders',
  'save',
])

function updateField(key, value) {
  emit('update-config-field', { key, value })
}
</script>

<template>
  <UiDialog
    :open="open"
    keep-mounted
    :title="title"
    :description="description"
    @update:open="$emit('update:open', $event)"
  >
    <div v-if="loadingToolConfig" class="config-loading-state">
      <UiBadge variant="secondary">加载中</UiBadge>
      <p>正在同步当前工具配置，请稍候。</p>
    </div>

    <div v-else-if="currentConfigTool.toolId === 'ear_declaration_data_fetcher'" class="config-form">
      <div class="form-field">
        <UiLabel for="ear-excel-file-path">申报数据 Excel 文件</UiLabel>
        <div class="folder-select-header">
          <UiLabel for="ear-excel-file-path">申报数据 Excel 文件</UiLabel>
          <UiButton variant="outline" @click="$emit('download-ear-template')">
            下载模板
          </UiButton>
        </div>
        <UiInput
          id="ear-excel-file-path"
          :model-value="configData.excelFilePath || configData.excelFileDisplay || configData.excelFolderPath || configData.excelFolderDisplay"
          placeholder="请填写申报数据 Excel 的绝对路径"
          @update:model-value="$emit('update-ear-excel-file-path', $event)"
        />
        <small class="field-hint">当前会校验该 Excel 文件是否已填写；运行时只读取这一个表，不再扫描整个文件夹。</small>
      </div>

      <div class="form-field">
        <UiLabel for="ear-report-year">检测年份</UiLabel>
        <UiInput
          id="ear-report-year"
          :model-value="configData.reportYear"
          placeholder="例如 2026"
          @update:model-value="value => updateField('reportYear', String(value || '').trim())"
        />
      </div>

      <div class="form-field">
        <UiLabel for="ear-report-month-german">检测月份（德语）</UiLabel>
        <UiInput
          id="ear-report-month-german"
          :model-value="configData.reportMonthGerman"
          placeholder="例如 März"
          @update:model-value="value => updateField('reportMonthGerman', String(value || '').trim())"
        />
      </div>

      <div class="form-field">
        <small class="field-hint">表头需包含：授权代表\nbevollmächtigter Vertreter、WEEE号\nWEEE-Nummer、中文名\nFirmenname auf Chinesisch、英文名\nFirmenname auf Englisch、类别\nKategorie、德语类目、账号、密码、*月申报数据、官网上抓取的数据（*月）。年份和德语月份从配置项读取，不再从 Excel 表中读取。</small>
        <small class="field-hint">可先点击“下载模板”获取 Excel 示例。</small>
      </div>
    </div>

    <div v-else-if="currentConfigTool.toolId !== 'citeo_email_extractor'" class="config-form">
      <div class="form-field">
        <UiLabel for="folder-path">递延税单据总文件夹</UiLabel>
        <UiInput
          id="folder-path"
          :model-value="configData.folderPath || configData.folderDisplay"
          placeholder="请填写部署电脑可访问的真实绝对路径，例如 \\\\服务器\\共享\\顾问部\\英德单据"
          @update:model-value="$emit('update-invoice-folder-path', $event)"
        />
        <small class="field-hint">仅支持手动填写真实路径。保存或运行时会校验目录是否可读可写，且必须在当前部门共享根目录下；像 `C:\\Users\\...` 这类用户本机路径会被拦截。</small>
      </div>

      <div class="form-field">
        <UiLabel for="list-excel-path">Excel 清单文件</UiLabel>
        <UiInput
          id="list-excel-path"
          :model-value="configData.listExcelPath || configData.listExcelDisplay"
          placeholder="请填写部署电脑可访问的 .xlsx 真实绝对路径"
          @update:model-value="$emit('update-invoice-excel-path', $event)"
        />
        <small class="field-hint">保存或运行时会校验 Excel 文件是否可读，并同时确认该路径属于当前部门共享根目录。</small>
      </div>
    </div>

    <div v-else class="config-form">
      <div class="form-field">
        <UiLabel for="email">163 邮箱账号</UiLabel>
        <UiInput
          id="email"
          :model-value="configData.email"
          type="email"
          placeholder="your_email@163.com"
          disabled
          @update:model-value="value => updateField('email', value)"
        />
      </div>

      <div class="form-field">
        <small class="field-hint">提示：点击“加载文件夹”，选择存放注销邮件的文件夹，填写获取邮件数量后保存配置即可运行。邮箱和授权码已预配置，如需修改请联系管理员。</small>
      </div>

      <div class="form-field">
        <div class="folder-select-header">
          <UiLabel for="mail-folder">选择邮件文件夹（存放注销邮件的文件夹）</UiLabel>
          <UiButton
            variant="outline"
            size="sm"
            :loading="loadingFolders"
            :disabled="!configData.email"
            @click="$emit('load-mail-folders')"
          >
            {{ mailFolders.length > 0 ? '刷新' : '加载文件夹' }}
          </UiButton>
        </div>
        <UiSelect
          id="mail-folder"
          :model-value="configData.selectedFolder"
          :disabled="mailFolders.length === 0"
          :options="folderOptions"
          placeholder="请选择文件夹"
          :searchable="false"
          @update:model-value="value => updateField('selectedFolder', value)"
        />
        <small v-if="mailFoldersError" class="field-error">{{ mailFoldersError }}</small>
      </div>

      <div class="form-field">
        <UiLabel for="max-emails">邮件数量限制</UiLabel>
        <UiInput
          id="max-emails"
          :model-value="String(configData.maxEmails)"
          type="number"
          placeholder="50"
          @update:model-value="value => updateField('maxEmails', value)"
        />
      </div>
    </div>

    <template #footer>
      <UiButton
        variant="outline"
        :disabled="savingToolConfig"
        @click="$emit('update:open', false)"
      >
        取消
      </UiButton>
      <UiButton
        :loading="savingToolConfig"
        :disabled="loadingToolConfig || savingToolConfig"
        @click="$emit('save')"
      >
        保存配置
      </UiButton>
    </template>
  </UiDialog>
</template>

<style scoped>
.field-hint {
  display: block;
  margin-top: 0.25rem;
  font-size: 0.75rem;
  color: var(--muted);
}

.field-error {
  display: block;
  margin-top: 0.25rem;
  font-size: 0.75rem;
  color: var(--danger);
}

.config-loading-state {
  display: grid;
  gap: 0.75rem;
  padding: 0.25rem 0 0.5rem;
}

.config-loading-state p {
  margin: 0;
  color: var(--muted-foreground);
  line-height: 1.6;
}

.form-field > :deep(.ui-label):has(+ .folder-select-header) {
  display: none;
}

.folder-select-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

@media (max-width: 980px) {
  .folder-select-header {
    display: grid;
    gap: 0.5rem;
  }
}
</style>
