<script setup lang="ts">
  import type { ShiftAdvice } from '@virtual-tcu/shared/config/hud'
  import HudChrome from '../HudChrome.vue'
  import HudPedalGauge from '../HudPedalGauge.vue'
  import HudRpmSegments from '../HudRpmSegments.vue'

  defineProps<{
    mode: string
    modeColor: string
    tcuState: string
    clickThrough: boolean
    connected: boolean
    live: boolean
    gearLabel: string
    gearStyle: Record<string, string>
    speed: number
    rpm: number
    rpmMax: number
    rpmPct: number
    rpmBarColor: string
    throttle: number
    brake: number
    shiftAdvice: ShiftAdvice
    showShiftAdvisor: boolean
    crossoverLearnState: string
    relearnStatus?: string
    relearnStatusRpm?: number
    learnMatureGears?: number
    learnTargetGears?: number
    clutchAssistEnabled?: boolean
    transmissionType?: 'sequential' | 'clutch' | 'unknown'
  }>()

  const emit = defineEmits<{
    toggleClickThrough: [e: MouseEvent]
    close: []
  }>()
</script>

<template>
  <div class="tpl-racing">
    <HudRpmSegments :rpm-pct="rpmPct" :rpm-max="rpmMax" :segments="16" variant="bar8" />

    <div class="dash-row">
      <div class="col speed-col">
        <span class="val">{{ speed }}</span>
        <span class="lbl">KM/H</span>
      </div>

      <div class="col gear-col">
        <div class="gear" :style="gearStyle">{{ gearLabel }}</div>
        <div
          class="gear-advice"
          :class="{
            active: showShiftAdvisor && (shiftAdvice === 'up' || shiftAdvice === 'down'),
            up: shiftAdvice === 'up',
            down: shiftAdvice === 'down',
          }"
          aria-hidden="true"
        >
          <svg
            v-if="showShiftAdvisor && shiftAdvice === 'up'"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
          >
            <path d="M12 19V5M6 11l6-6 6 6" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <svg
            v-else-if="showShiftAdvisor && shiftAdvice === 'down'"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
          >
            <path d="M12 5v14M6 13l6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>
      </div>

      <div class="col pedals-col">
        <HudPedalGauge label="THR" :value="throttle" compact />
        <HudPedalGauge label="BRK" :value="brake" compact />
      </div>
    </div>

    <div v-if="!connected" class="hud-status warn">backend offline</div>
    <div v-else-if="!live" class="hud-status dim">awaiting telemetry…</div>

    <HudChrome
      stacked
      footer
      :mode="mode"
      :mode-color="modeColor"
      :tcu-state="tcuState"
      :click-through="clickThrough"
      :learn-state="crossoverLearnState"
      :relearn-status="relearnStatus"
      :relearn-status-rpm="relearnStatusRpm"
      :learn-mature-gears="learnMatureGears"
      :learn-target-gears="learnTargetGears"
      :clutch-assist-enabled="clutchAssistEnabled"
      :transmission-type="transmissionType"
      @toggle-click-through="emit('toggleClickThrough', $event)"
      @close="emit('close')"
    />
  </div>
</template>

<style scoped>
  .tpl-racing {
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: 350px;
  }

  .dash-row {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    gap: 12px;
    padding: 4px 2px 0;
  }

  .col {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .speed-col {
    align-items: flex-start;
  }

  .gear-col {
    align-items: center;
    min-height: 76px;
  }

  .pedals-col {
    align-items: flex-end;
    gap: 6px;
  }

  .val {
    font-size: 28px;
    font-weight: 900;
    font-style: italic;
    line-height: 1;
    color: #f8fafc;
    letter-spacing: -0.02em;
  }

  .lbl {
    font-size: 8px;
    letter-spacing: 0.16em;
    color: #94a3b8;
    margin-top: 2px;
    font-weight: 600;
  }

  .gear {
    font-size: 64px;
    font-weight: 900;
    font-style: italic;
    line-height: 1;
    letter-spacing: -0.04em;
    min-width: 72px;
    text-align: center;
  }

  .gear-advice {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 16px;
    margin-top: -2px;
    opacity: 0;
    visibility: hidden;
    pointer-events: none;
  }

  .gear-advice svg {
    width: 16px;
    height: 16px;
  }

  .gear-advice.active {
    opacity: 1;
    visibility: visible;
  }

  .gear-advice.up {
    color: #22c55e;
    filter: drop-shadow(0 0 5px rgba(34, 197, 94, 0.55));
  }

  .gear-advice.down {
    color: #eab308;
    filter: drop-shadow(0 0 5px rgba(234, 179, 8, 0.55));
  }
</style>
