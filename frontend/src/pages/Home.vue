<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const d = ref(null)
const err = ref('')
async function load() {
  err.value = ''
  try { d.value = await api.dashboard() } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <div class="grid" v-if="d">
      <div class="stat"><div class="k">业务日</div><div class="v">{{ d.business_day }}</div></div>
      <div class="stat"><div class="k">今日事件</div><div class="v">{{ d.event_count }}</div></div>
      <div class="stat"><div class="k">核销事实（已入湖）</div><div class="v ticket">{{ d.fact_count }}</div></div>
      <div class="stat"><div class="k">待钉 open</div><div class="v">{{ d.open_fact_count }}</div></div>
      <div class="stat"><div class="k">今日核销额</div><div class="v ticket">{{ d.redeem_total_today }}</div></div>
      <div class="stat"><div class="k">日已钉扎</div><div class="v">{{ d.day_sealed ? '是' : '否' }}</div></div>
      <div class="stat"><div class="k">缓冲回执</div><div class="v">{{ d.buffer_count }}</div></div>
      <div class="stat">
        <div class="k">未冲刷缓冲（笔/额）</div>
        <div class="v" :class="{ ticket: d.buffer_count > 0 }">
          {{ d.buffer_count }} / {{ d.buffer_amount }}
        </div>
      </div>
      <div class="stat"><div class="k">缓冲失败</div><div class="v" :class="{ ticket: d.buffer_failed_count > 0 }">{{ d.buffer_failed_count }}</div></div>
      <div class="stat">
        <div class="k">钉扎冲刷策略</div>
        <div class="v" style="font-size:.95rem">
          {{ d.seal_flush_policy === 'seal_with_dirty_buffer' ? '带脏缓冲钉扎' : '钉前强制冲刷' }}
        </div>
      </div>
    </div>
    <p class="msg" v-if="!err">
      核销先进缓冲、再冲刷落事件/事实；未冲刷缓冲单独计数，不会被当成已入湖事实或写进 sealed 明细。
      <template v-if="d && d.buffer_count > 0">当前有 <strong>{{ d.buffer_count }}</strong> 笔核销仍在缓冲。</template>
    </p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>
</template>
