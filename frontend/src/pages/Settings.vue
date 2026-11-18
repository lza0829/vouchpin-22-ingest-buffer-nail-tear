<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
const day = ref('')
const policy = ref(null)
const msg = ref('')
const err = ref('')

async function load() {
  try {
    const r = await api.getDay()
    day.value = r.business_day
    policy.value = await api.getSealPolicy()
  } catch (e) { err.value = e.message }
}
async function saveDay() {
  msg.value = ''; err.value = ''
  try {
    const r = await api.setDay(day.value)
    msg.value = `业务日已设为 ${r.business_day}`
  } catch (e) { err.value = e.message }
}
async function savePolicy(p) {
  msg.value = ''; err.value = ''
  try {
    const r = await api.setSealPolicy(p)
    policy.value = await api.getSealPolicy()
    msg.value = `钉扎冲刷策略已切换为「${r.label}」（全局互斥，即刻生效）`
  } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <div class="row">
      <label>业务日 <input v-model="day" placeholder="YYYY-MM-DD" /></label>
      <button type="button" @click="saveDay">保存</button>
    </div>
  </div>
  <div class="panel" v-if="policy">
    <h3 style="margin:0 0 .5rem">钉前缓冲冲刷策略（全局互斥，二选一）</h3>
    <div class="row" style="align-items:flex-start;flex-direction:column;gap:.5rem">
      <label v-for="opt in policy.options" :key="opt.policy"
        style="display:flex;gap:.5rem;align-items:flex-start;max-width:46rem">
        <input type="radio" name="seal-policy" :value="opt.policy"
          :checked="policy.policy === opt.policy"
          @change="savePolicy(opt.policy)" />
        <span>
          <strong>{{ opt.label }}</strong>
          <template v-if="opt.policy === 'flush_before_seal'">
            ——钉扎开始先 flush 该业务日缓冲至事件与事实；冲刷失败则拒钉；
            批次明细只来自冲刷后 open 事实；缓冲残留必须为 0。
          </template>
          <template v-else>
            ——可不 flush；本批只钉已落库 open 事实；批次快照 buffer_remaining 与指纹；
            总览显示未冲刷缓冲；仍在缓冲、未落库的核销禁止写入 sealed 明细。
          </template>
        </span>
      </label>
    </div>
    <p class="msg" v-if="msg">{{ msg }}</p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>
</template>
