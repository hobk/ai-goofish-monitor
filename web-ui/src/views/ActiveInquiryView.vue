<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Bot, MessageCircleMore, RefreshCw, Save, Square } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { toast } from '@/components/ui/toast'
import { useActiveInquiry, type ActiveInquiry } from '@/composables/useActiveInquiry'

const {
  settings,
  inquiries,
  selectedInquiry,
  messages,
  isLoading,
  error,
  saveSettings,
  loadDetail,
  startInquiry,
  stopInquiry,
  refresh,
} = useActiveInquiry()

const settingsDraft = ref({ ...settings.value })

function syncDraft() {
  settingsDraft.value = { ...settings.value }
}

async function handleRefresh() {
  await refresh()
  syncDraft()
}

async function handleSaveSettings() {
  try {
    await saveSettings(settingsDraft.value)
    syncDraft()
    toast({ title: '主动咨询配置已保存' })
  } catch (e) {
    toast({ title: '保存失败', description: (e as Error).message, variant: 'destructive' })
  }
}

async function selectInquiry(inquiry: ActiveInquiry) {
  await loadDetail(inquiry.id)
}

function statusTone(status: string) {
  if (status === 'running') return 'default'
  if (status === 'done') return 'secondary'
  if (status === 'failed') return 'destructive'
  return 'outline'
}

onMounted(handleRefresh)
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="text-2xl font-bold text-slate-900">主动咨询</h1>
        <p class="mt-1 text-sm text-slate-500">推荐商品达到阈值后，自动创建闲鱼会话，由 AI 咨询和议价，并记录全过程。</p>
      </div>
      <Button variant="outline" :disabled="isLoading" @click="handleRefresh">
        <RefreshCw class="h-4 w-4" />刷新
      </Button>
    </div>

    <div v-if="error" class="app-alert-error" role="alert">{{ error.message }}</div>

    <Card>
      <CardHeader>
        <CardTitle class="flex items-center gap-2"><Bot class="h-5 w-5" />模块配置</CardTitle>
        <CardDescription>提示词文件默认是 prompts/active_inquiry_prompt.txt，可在 Prompt 管理里维护。</CardDescription>
      </CardHeader>
      <CardContent class="grid gap-4 md:grid-cols-3">
        <label class="flex items-center gap-2 rounded-lg border p-3 text-sm font-medium">
          <input v-model="settingsDraft.enabled" type="checkbox" class="h-4 w-4" />启用主动咨询
        </label>
        <label class="space-y-1 text-sm">
          <span class="font-medium">推荐度阈值(%)</span>
          <Input v-model="settingsDraft.threshold" type="number" min="0" max="100" />
        </label>
        <label class="space-y-1 text-sm">
          <span class="font-medium">最大回复轮数</span>
          <Input v-model="settingsDraft.max_rounds" type="number" min="1" max="30" />
        </label>
        <label class="space-y-1 text-sm">
          <span class="font-medium">目标砍价幅度(%)</span>
          <Input v-model="settingsDraft.bargain_percent" type="number" min="0" max="80" />
        </label>
        <label class="space-y-1 text-sm md:col-span-2">
          <span class="font-medium">账号状态文件</span>
          <Input v-model="settingsDraft.account_state_file" placeholder="留空则使用 state/ 下第一个账号；如 state/xy-0837.json" />
        </label>
        <label class="space-y-1 text-sm md:col-span-2">
          <span class="font-medium">提示词文件</span>
          <Input v-model="settingsDraft.prompt_file" />
        </label>
        <label class="flex items-center gap-2 rounded-lg border p-3 text-sm font-medium">
          <input v-model="settingsDraft.auto_send" type="checkbox" class="h-4 w-4" />AI 生成后自动发送
        </label>
        <label class="flex items-center gap-2 rounded-lg border p-3 text-sm font-medium">
          <input v-model="settingsDraft.captcha_solver_enabled" type="checkbox" class="h-4 w-4" />启用外部滑块服务
        </label>
        <label class="space-y-1 text-sm md:col-span-2">
          <span class="font-medium">滑块服务接口</span>
          <Input v-model="settingsDraft.captcha_solver_endpoint" placeholder="https://xy-auto.yfw.me/api/v1/captcha/slider-solve" />
        </label>
        <label class="space-y-1 text-sm">
          <span class="font-medium">滑块服务密钥</span>
          <Input v-model="settingsDraft.captcha_solver_api_key" type="password" autocomplete="new-password" placeholder="已保存时显示 ********" />
        </label>
        <label class="space-y-1 text-sm">
          <span class="font-medium">滑块超时(秒)</span>
          <Input v-model="settingsDraft.captcha_solver_timeout" type="number" min="20" max="120" />
        </label>
        <label class="flex items-center gap-2 rounded-lg border p-3 text-sm font-medium md:col-span-2">
          <input v-model="settingsDraft.captcha_solver_pass_cookies" type="checkbox" class="h-4 w-4" />调用滑块服务时传递当前账号 Cookie 与 device_id
        </label>
        <div class="md:col-span-3 flex justify-end">
          <Button @click="handleSaveSettings"><Save class="h-4 w-4" />保存配置</Button>
        </div>
      </CardContent>
    </Card>

    <div class="grid gap-6 lg:grid-cols-[420px_1fr]">
      <Card>
        <CardHeader>
          <CardTitle>咨询队列</CardTitle>
          <CardDescription>展示由推荐商品自动创建的咨询/砍价流程。</CardDescription>
        </CardHeader>
        <CardContent class="space-y-3">
          <button
            v-for="item in inquiries"
            :key="item.id"
            class="w-full rounded-xl border p-3 text-left transition hover:border-primary/50 hover:bg-primary/5"
            :class="selectedInquiry?.id === item.id ? 'border-primary bg-primary/5' : 'border-slate-200'"
            @click="selectInquiry(item)"
          >
            <div class="flex items-center justify-between gap-2">
              <p class="line-clamp-1 font-semibold text-slate-800">{{ item.title || item.item_id }}</p>
              <Badge :variant="statusTone(item.status) as any">{{ item.status }}</Badge>
            </div>
            <p class="mt-1 text-xs text-slate-500">推荐度 {{ item.score }}% · ¥{{ item.price || '-' }} → 目标 ¥{{ item.target_price || '-' }}</p>
            <p class="mt-1 text-xs text-slate-400">卖家 {{ item.seller_nickname || item.seller_id }} · {{ item.updated_at }}</p>
          </button>
          <p v-if="!inquiries.length" class="rounded-xl border border-dashed p-6 text-center text-sm text-slate-400">暂无主动咨询记录</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div class="flex items-start justify-between gap-4">
            <div>
              <CardTitle class="flex items-center gap-2"><MessageCircleMore class="h-5 w-5" />沟通过程</CardTitle>
              <CardDescription v-if="selectedInquiry">{{ selectedInquiry.title }} / chat_id: {{ selectedInquiry.chat_id || '-' }}</CardDescription>
              <CardDescription v-else>请选择左侧咨询记录查看完整上下文。</CardDescription>
            </div>
            <div v-if="selectedInquiry" class="flex gap-2">
              <Button size="sm" variant="outline" @click="startInquiry(selectedInquiry.id)">启动/重试</Button>
              <Button size="sm" variant="destructive" @click="stopInquiry(selectedInquiry.id)"><Square class="h-4 w-4" />停止</Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div v-if="selectedInquiry" class="mb-4 grid gap-2 rounded-xl bg-slate-50 p-4 text-sm md:grid-cols-3">
            <div><span class="text-slate-500">状态：</span>{{ selectedInquiry.status }} / {{ selectedInquiry.stage }}</div>
            <div><span class="text-slate-500">轮数：</span>{{ selectedInquiry.rounds }}</div>
            <div><span class="text-slate-500">账号：</span>{{ selectedInquiry.account_id || '-' }}</div>
          </div>
          <div class="space-y-3">
            <div
              v-for="msg in messages"
              :key="msg.id"
              class="rounded-xl border p-3"
              :class="msg.direction === 'out' ? 'ml-8 border-emerald-100 bg-emerald-50' : msg.direction === 'in' ? 'mr-8 border-blue-100 bg-blue-50' : 'border-slate-200 bg-slate-50'"
            >
              <div class="mb-1 text-xs font-semibold text-slate-500">{{ msg.direction }} · {{ msg.role }} · {{ msg.created_at }}</div>
              <p class="whitespace-pre-wrap text-sm text-slate-800">{{ msg.content }}</p>
            </div>
            <p v-if="selectedInquiry && !messages.length" class="text-center text-sm text-slate-400">暂无消息</p>
            <p v-if="!selectedInquiry" class="text-center text-sm text-slate-400">未选择咨询记录</p>
          </div>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
