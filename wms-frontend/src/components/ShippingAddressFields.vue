<template>
  <div class="grid grid-cols-[1fr_1fr_110px] gap-2">
    <label class="field-label">{{ nameLabel }}
      <input v-model="model.contact_name" class="field w-full mt-1" maxlength="50" :required="required" />
    </label>
    <label class="field-label">연락처
      <input v-model="model.contact_phone" class="field w-full mt-1" maxlength="20" placeholder="010-1234-5678" :required="required" />
    </label>
    <label class="field-label">우편번호
      <input v-model="model.zipcode" class="field w-full mt-1" maxlength="5" inputmode="numeric" pattern="\d{5}" placeholder="5자리" :required="required" />
    </label>
    <label class="field-label col-span-2">주소
      <input v-model="model.address" class="field w-full mt-1" maxlength="200" placeholder="도로명 주소" :required="required" />
    </label>
    <label class="field-label">상세주소
      <input v-model="model.address_detail" class="field w-full mt-1" maxlength="100" />
    </label>
  </div>
</template>

<script setup>
// 택배 배송지·회수지 입력 칸. model 객체의 contact_name 등 값을 직접 채웁니다.
defineProps({
  model: { type: Object, required: true },
  nameLabel: { type: String, default: '받는 분' },
  required: { type: Boolean, default: true },
})
</script>
