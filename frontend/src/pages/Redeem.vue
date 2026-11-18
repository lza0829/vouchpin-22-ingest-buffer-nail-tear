<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const preview = ref(null)
const msg = ref('')
const err = ref('')

const policyLabel = computed(() => {
  const p = preview.value?.flush_policy
  if (p === 'flush_before_seal') return '钉前强制冲刷'
  if (p === 'seal_with_dirty_buffer') return '允许带脏缓冲钉扎'
  return '—'
})
const bufferItems = computed(() => preview.value?.buffer?.items || [])

async function load() {
  err.value = ''
  try { preview.value = await api.preview() } catch (e) { err.value = e.message }
}
async function flushBuffer() {
  msg.value = ''; err.value = ''
  try {
    const r = await api.flush({ business_day: preview.value.business_day })
    const failed = r.days?.flatMap((d) => d.failed.map((f) => `#${f.buffer_id}:${f.error}`)) || []
    msg.value = `已冲刷 ${r.flushed} 笔，缓冲残留 ${r.remaining}` + (failed.length ? `；失败：${failed.join('；')}` : '')
    await load()
  } catch (e) { err.value = e.message }
}
async function seal() {
  msg.value = ''; err.value = ''
  try {
    const r = await api.seal({ business_day: preview.value.business_day })
    const bufNote = r.buffer_remaining > 0
      ? `；批次快照未冲刷缓冲 ${r.buffer_remaining} 笔 / ${r.buffer_amount}（指纹 ${r.buffer_fingerprint.slice(0, 10)}…）`
      : '；缓冲残留为 0'
    msg.value = `已钉扎批次 #${r.batch_id} · ${r.fact_count} 笔 · 合计 ${r.total_amount}${bufNote}`
    await load()
  } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
<template>
  <div class="panel" v-if="preview">
    <div class="grid">
      <div class="stat"><div class="k">业务日</div><div class="v">{{ preview.business_day }}</div></div>
      <div class="stat"><div class="k">钉扎冲刷策略</div><div class="v" style="font-size:1.05rem">{{ policyLabel }}</div></div>
      <div class="stat">
        <div class="k">待钉 open（已落库）</div>
        <div class="v ticket">{{ preview.open_count }}</div>
      </div>
      <div class="stat"><div class="k">待钉合计</div><div class="v ticket">{{ preview.open_total }}</div></div>
      <div class="stat">
        <div class="k">未冲刷缓冲</div>
        <div class="v" :class="{ ticket: preview.buffer.remaining > 0 }">{{ preview.buffer.remaining }}</div>
      </div>
      <div class="stat"><div class="k">已钉扎</div><div class="v">{{ preview.already_sealed ? '是' : '否' }}</div></div>
    </div>

    <div class="row">
      <button type="button" @click="seal"
        :disabled="preview.already_sealed || preview.open_count === 0">钉扎本日核销</button>
      <button type="button" class="ghost" @click="flushBuffer"
        :disabled="preview.buffer.remaining === 0">手动冲刷缓冲</button>
      <button type="button" class="ghost" @click="load">刷新预览</button>
    </div>
    <p class="msg err" v-if="err">{{ err }}</p>
    <p class="msg" v-if="msg">{{ msg }}</p>
  </div>

  <div class="panel" v-if="preview && preview.buffer.remaining > 0">
    <h3 style="margin:0 0 .6rem">未冲刷缓冲（未落事件/事实，禁止计入 sealed 明细）</h3>
    <table>
      <thead><tr><th>缓冲ID</th><th>券码</th><th>活动</th><th>金额</th><th>状态</th><th>错误</th></tr></thead>
      <tbody>
        <tr v-for="b in bufferItems" :key="b.id">
          <td>{{ b.id }}</td>
          <td>{{ b.coupon_code }}</td>
          <td>{{ b.campaign_code }}</td>
          <td>{{ b.amount }}</td>
          <td><span class="tag" :class="{ warn: b.flush_status === 'failed' }">{{ b.flush_status }}</span></td>
          <td style="color:var(--bad)">{{ b.flush_error }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="panel">
    <h3 style="margin:0 0 .6rem">已落库 open 核销事实（钉扎明细唯一来源）</h3>
    <table>
      <thead><tr><th>事实ID</th><th>券码</th><th>活动</th><th>金额</th><th>状态</th></tr></thead>
      <tbody>
        <tr v-for="f in (preview?.facts || [])" :key="f.id">
          <td>{{ f.id }}</td>
          <td>{{ f.coupon_code }}</td>
          <td>{{ f.campaign_code }}</td>
          <td>{{ f.amount }}</td>
          <td><span class="tag warn">{{ f.status }}</span></td>
        </tr>
        <tr v-if="preview && preview.facts.length === 0">
          <td colspan="5" style="color:var(--muted)">暂无已落库 open 事实（缓冲中的核销不会出现在这里）</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
