<script setup lang="ts">
  import { NCard, NFlex, NRadioButton, NRadioGroup, NSwitch } from 'naive-ui'
  import { inject, nextTick, ref, watch } from 'vue'
  import { settingsContextKey } from './context'

  const ctx = inject(settingsContextKey)!
  const { t, store } = ctx
  const logView = ref<'system' | 'telemetry'>('system')
  const autoScroll = ref(true)
  const sysLogRef = ref<HTMLElement | null>(null)

  watch(
    () => store.systemLogs.value.length,
    () => {
      if (logView.value === 'system' && autoScroll.value && sysLogRef.value) {
        nextTick(() => {
          sysLogRef.value!.scrollTop = sysLogRef.value!.scrollHeight
        })
      }
    },
  )
</script>

<template>
  <NFlex vertical :size="16">
    <NCard
      size="small"
      :bordered="false"
      style="
        padding: 0;
        background: #18181c;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      "
    >
      <template #header>
        <NFlex justify="space-between" align="center">
          <NRadioGroup v-model:value="logView" size="small">
            <NRadioButton value="system" :label="t('logs.systemLogs')" />
            <NRadioButton value="telemetry" :label="t('logs.telemetryLogs')" />
          </NRadioGroup>
          <NSwitch v-model:value="autoScroll" size="small">
            <template #checked>{{ t('logs.autoScroll') }}</template>
            <template #unchecked>{{ t('logs.scrollLock') }}</template>
          </NSwitch>
        </NFlex>
      </template>

      <div
        v-if="logView === 'system'"
        ref="sysLogRef"
        style="height: 360px; overflow-y: auto; padding: 10px; font-size: 11px"
      >
        <div
          v-if="store.systemLogs.value.length === 0"
          style="color: #666; text-align: center; margin-top: 40px"
        >
          {{ t('logs.waitingSystemEvents') }}
        </div>
        <div
          v-for="(log, i) in store.systemLogs.value"
          :key="i"
          style="margin-bottom: 4px; white-space: pre-wrap"
        >
          <span style="color: #888"
            >[{{ new Date(log.time).toISOString().substring(11, 23) }}]</span
          >
          <span
            :style="{
              color:
                log.level === 'ERROR'
                  ? '#ff4d4f'
                  : log.level === 'WARN'
                    ? '#faad14'
                    : log.level === 'DEBUG'
                      ? '#a3a3a3'
                      : '#69b1ff',
              margin: '0 8px',
            }"
          >
            [{{ log.level }}]
          </span>
          <span style="color: #ddd">{{ log.msg }}</span>
        </div>
      </div>

      <div v-else style="height: 360px; overflow-y: auto; padding: 10px; font-size: 11px">
        <div
          v-if="store.telemetryLogs.value.length === 0"
          style="color: #666; text-align: center; margin-top: 40px"
        >
          {{ t('logs.noSnapshotsRecorded') }}
        </div>
        <div
          v-for="(log, i) in store.telemetryLogs.value"
          :key="i"
          style="
            margin-bottom: 8px;
            background: rgba(255, 255, 255, 0.05);
            padding: 8px;
            border-radius: 4px;
          "
        >
          <NFlex justify="space-between" align="center">
            <span style="color: #888"
              >[{{ new Date(log.time).toISOString().substring(11, 23) }}]</span
            >
            <span style="color: #ffccc7; font-weight: bold">{{ log.reason }}</span>
          </NFlex>
          <div style="margin-top: 4px; color: #4ade80">
            {{ t('logs.saved') }} {{ log.filename }}
          </div>
        </div>
      </div>
    </NCard>
  </NFlex>
</template>
