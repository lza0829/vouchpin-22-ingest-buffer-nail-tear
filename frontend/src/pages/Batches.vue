<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref([])
const err = ref('')
const openId = ref(null)
const detail = ref(null)

async function load() {
  try { rows.value = await api.batches() } catch (e) { err.value = e.message }
}
async function toggle(b) {
  if (openId.value === b.id) { openId.value = null; detail.value = null; return }
  openId.value = b.id
  detail.value = await api.batch(b.id)
}
function shortFp(fp) {
  return fp ? fp.slice(0, 10) + '…' : '—'
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <p class="msg err" v-if="err">{{ err }}</p>
    <table>
      <thead>
        <tr>
          <th>批次</th><th>业务日</th><th>状态</th><th>笔数</th><th>合计</th>
          <th>钉扎时缓冲残留</th><th>缓冲指纹</th><th>钉扎时刻</th><th></th>
        </tr>
      </thead>
      <tbody>
        <template v-for="b in rows" :key="b.id">
          <tr>
            <td>{{ b.id }}</td>
            <td>{{ b.business_day }}</td>
            <td><span class="tag ok">{{ b.status }}</span></td>
            <td>{{ b.fact_count }}</td>
            <td>{{ b.total_amount }}</td>
            <td>
              <span :class="{ 'tag warn': b.buffer_remaining > 0 }">
                {{ b.buffer_remaining }} 笔 / {{ b.buffer_amount }}
              </span>
            </td>
            <td style="font-family:monospace;font-size:.8rem">{{ shortFp(b.buffer_fingerprint) }}</td>
            <td>{{ b.sealed_at }}</td>
            <td><button type="button" class="ghost" @click="toggle(b)">
              {{ openId === b.id ? '收起' : '明细' }}
            </button></td>
          </tr>
          <tr v-if="openId === b.id && detail">
            <td colspan="9">
              <p class="msg" style="margin:.3rem 0">
                sealed 明细仅含已落库事实（{{ detail.facts.length }} 笔）；缓冲残留
                {{ detail.buffer_remaining }} 笔不在其中。
              </p>
              <table>
                <thead><tr><th>事实ID</th><th>券码</th><th>活动</th><th>金额</th><th>状态</th><th>事件ID</th></tr></thead>
                <tbody>
                  <tr v-for="f in detail.facts" :key="f.id">
                    <td>{{ f.id }}</td><td>{{ f.coupon_code }}</td><td>{{ f.campaign_code }}</td>
                    <td>{{ f.amount }}</td><td>{{ f.status }}</td><td>{{ f.event_id }}</td>
                  </tr>
                </tbody>
              </table>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>
