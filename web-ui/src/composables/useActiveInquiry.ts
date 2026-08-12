import { ref } from 'vue'
import { http } from '@/lib/http'

export interface ActiveInquirySettings {
  enabled: boolean
  threshold: number
  max_rounds: number
  bargain_percent: number
  prompt_file: string
  account_state_file: string
  auto_send: boolean
}

export interface ActiveInquiry {
  id: number
  item_id: string
  seller_id: string
  seller_nickname?: string
  task_name?: string
  keyword?: string
  title?: string
  price?: number
  target_price?: number
  score: number
  status: string
  stage: string
  chat_id?: string
  account_id?: string
  rounds: number
  created_at: string
  updated_at: string
}

export interface ActiveInquiryMessage {
  id: number
  inquiry_id: number
  direction: 'in' | 'out' | 'system'
  role: string
  content: string
  created_at: string
}

const defaultSettings: ActiveInquirySettings = {
  enabled: false,
  threshold: 70,
  max_rounds: 6,
  bargain_percent: 10,
  prompt_file: 'prompts/active_inquiry_prompt.txt',
  account_state_file: '',
  auto_send: true,
}

export function useActiveInquiry() {
  const settings = ref<ActiveInquirySettings>({ ...defaultSettings })
  const inquiries = ref<ActiveInquiry[]>([])
  const selectedInquiry = ref<ActiveInquiry | null>(null)
  const messages = ref<ActiveInquiryMessage[]>([])
  const isLoading = ref(false)
  const error = ref<Error | null>(null)

  async function loadSettings() {
    settings.value = await http('/api/active-inquiry/settings')
  }

  async function saveSettings(payload: ActiveInquirySettings) {
    settings.value = await http('/api/active-inquiry/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  }

  async function loadInquiries(status?: string) {
    const data = await http('/api/active-inquiry/inquiries', { params: { status } })
    inquiries.value = data.items || []
  }

  async function loadDetail(id: number) {
    const data = await http(`/api/active-inquiry/inquiries/${id}`)
    selectedInquiry.value = data.inquiry
    messages.value = data.messages || []
  }

  async function startInquiry(id: number) {
    await http(`/api/active-inquiry/inquiries/${id}/start`, { method: 'POST' })
    await loadDetail(id)
    await loadInquiries()
  }

  async function stopInquiry(id: number) {
    await http(`/api/active-inquiry/inquiries/${id}/stop`, { method: 'POST' })
    await loadDetail(id)
    await loadInquiries()
  }

  async function refresh() {
    isLoading.value = true
    error.value = null
    try {
      await Promise.all([loadSettings(), loadInquiries()])
      if (selectedInquiry.value) {
        await loadDetail(selectedInquiry.value.id)
      }
    } catch (e) {
      error.value = e as Error
    } finally {
      isLoading.value = false
    }
  }

  return {
    settings,
    inquiries,
    selectedInquiry,
    messages,
    isLoading,
    error,
    loadSettings,
    saveSettings,
    loadInquiries,
    loadDetail,
    startInquiry,
    stopInquiry,
    refresh,
  }
}
