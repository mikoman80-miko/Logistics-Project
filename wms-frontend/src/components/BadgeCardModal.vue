<template>
  <!-- 사원증 카드 인쇄. 카드 크기(약 86 x 54mm)로 인쇄해 사원증에 붙이거나 끼워 씁니다. -->
  <Teleport to="body">
    <div class="print-only modal-overlay print:static print:bg-transparent" @click.self="$emit('close')">
      <div class="modal w-[420px] print:shadow-none print:border-none print:w-auto print:max-h-none">
        <div class="modal-header print:hidden">사원증 인쇄</div>
        <div class="modal-content">
          <div class="w-[340px] h-[214px] mx-auto border-2 border-black rounded-lg p-3 flex flex-col justify-between bg-white text-black">
            <div class="flex justify-between items-start">
              <div>
                <div class="text-caption">WMS 현장작업자</div>
                <div class="text-[22px] font-bold leading-tight">{{ badge.name || badge.username }}</div>
                <div class="font-mono text-caption">{{ badge.username }}</div>
              </div>
            </div>
            <Barcode :value="badge.code" :height="56" :module-width="1.5" />
          </div>
          <div class="alert alert-warning mt-3 mb-0 print:hidden">사원증 바코드는 비밀번호와 같습니다. 잃어버리면 바로 [사원증 재발급]을 눌러 예전 것을 쓰지 못하게 하세요.</div>
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

defineProps({ badge: { type: Object, required: true } })  // { code, username, name }
defineEmits(['close'])
const print = () => window.print()
</script>
