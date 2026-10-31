<template>
  <table class="data-table">
    <thead>
      <tr>
        <th>상품</th>
        <th width="90">수량</th>
        <th width="60">삭제</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="(line, index) in lines" :key="index">
        <td>
          <select v-model="line.item" class="field w-full" required>
            <option :value="null" disabled>상품 선택</option>
            <option v-for="item in items" :key="item.id" :value="item.id">
              [{{ item.sku }}] {{ item.name }} (재고 {{ item.quantity }})
            </option>
          </select>
        </td>
        <td><input v-model.number="line.quantity" type="number" min="1" class="field field-num w-full" required /></td>
        <td class="text-center">
          <button type="button" class="btn btn-sm btn-danger" :disabled="lines.length === 1" @click="removeLine(index)">삭제</button>
        </td>
      </tr>
    </tbody>
  </table>
  <button type="button" class="btn btn-sm mt-1.5" @click="addLine">+ 품목 추가</button>
</template>

<script setup>
const props = defineProps({
  lines: { type: Array, required: true },
  items: { type: Array, required: true },
})

const addLine = () => { props.lines.push({ item: null, quantity: 1 }) }
const removeLine = (index) => { props.lines.splice(index, 1) }
</script>
