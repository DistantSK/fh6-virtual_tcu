<script setup lang="ts">
  import { localeOptions, onLocaleChange } from './locale-switcher'
</script>

<template>
  <label class="text-tcu-txt-muted flex items-center gap-2 text-xs">
    <span class="text-tcu-txt-dim">{{ $t('locale.label') }}</span>
    <select
      class="border-tcu-border bg-tcu-bg-2 text-tcu-txt rounded-md border px-2 py-1 text-xs"
      :value="$i18n.locale"
      @change="onLocaleChange"
    >
      <option v-for="opt in localeOptions" :key="opt.value" :value="opt.value">
        {{ $t(opt.labelKey) }}
      </option>
    </select>
  </label>
</template>
