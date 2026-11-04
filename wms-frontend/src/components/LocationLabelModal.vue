<template>
  <!-- 보관 위치 라벨. 랙에 붙여 두고 현장 화면에서 스캔해 위치를 확인합니다. -->
  <Teleport to="body">
    <div class="print-only modal-overlay print:static print:bg-transparent" @click.self="$emit('close')">
      <div class="modal w-[720px] print:shadow-none print:border-none print:w-full print:max-h-none">
        <div class="modal-header print:hidden">보관 위치 라벨 ({{ locations.length }}장)</div>
        <div class="modal-content grid grid-cols-2 gap-3 print:block">
          <div v-for="loc in locations" :key="loc.id"
            class="border-2 border-black p-3 text-center bg-white break-inside-avoid print:mb-3 print:inline-block print:w-[48%] print:mr-[2%]">
            <div class="text-[28px] font-bold leading-tight text-black">{{ loc.full_code }}</div>
            <div v-if="loc.description" class="text-caption text-muted truncate">{{ loc.description }}</div>
            <div class="my-2"><Barcode :value="loc.barcode" :height="56" /></div>
            <div class="font-mono text-caption">{{ loc.barcode }}</div>
          </div>
        </div>
        <div class="modal-footer print:hidden">
          <button class="btn btn-primary btn-lg" @click="print">인쇄</button>
          <button class="btn btn-lg" @click="$emit('close')">닫기</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import Barcode from './Barcode.vue'

defineProps({ locations: { type: Array, required: true } })
defineEmits(['close'])
const print = () => window.print()
</script>
