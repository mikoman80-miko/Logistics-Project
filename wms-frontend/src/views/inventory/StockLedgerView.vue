<template>
  <div class="flex flex-col w-full h-full box-border p-1.5">
    <!-- 상단 검색바 패널 -->
    <div class="panel mb-2.5">
      <div class="panel-header panel-title">검색 조건</div>
      <div class="p-2 flex items-center gap-1.5 text-body">
        <label>조회 기간:</label>
        <input v-model="startDate" type="date"
          class="field w-[130px]" />
        <span>~</span>
        <input v-model="endDate" type="date"
          class="field w-[130px]" />

        <button @click="fetchLedger"
          class="btn btn-success ml-2.5">조회
          실행</button>
        <button @click="exportExcel"
          class="btn ml-1">엑셀
          다운로드</button>
      </div>
    </div>

    <!-- 우측/하단 수불부 그리드 패널 -->
    <div class="panel flex-1 min-h-0">
      <div
        class="panel-header">
        <span class="panel-title">재고수불부 명세 (총 {{ ledgerList.length }}건)</span>
      </div>
      <div class="p-0 flex-1 overflow-y-auto">
        <table class="data-table data-table-sm">
          <thead>
            <tr>
              <th
               
                width="130">상품코드</th>
              <th
               >
                상품명</th>
              <th
               
                width="100">카테고리</th>
              <th
               
                width="100">보관 위치</th>
              <th
               
                width="90">기초재고</th>
              <th
               
                width="90">당기입고(+)</th>
              <th
               
                width="90">당기출고(-)</th>
              <th
               
                width="90">기말재고(=)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="ledgerList.length === 0">
              <td colspan="8" class="text-center">조회된 수불 내역이 없습니다.</td>
            </tr>
            <tr v-for="row in ledgerList" :key="row.sku">
              <td
                class="text-center font-mono font-bold text-primary whitespace-nowrap overflow-hidden text-ellipsis">
                {{ row.sku }}</td>
              <td class="whitespace-nowrap overflow-hidden text-ellipsis">{{
                row.name }}</td>
              <td
                class="text-center whitespace-nowrap overflow-hidden text-ellipsis">
                {{ row.category_name }}</td>
              <td
                class="text-center font-mono whitespace-nowrap overflow-hidden text-ellipsis">
                {{ row.location }}</td>
              <td class="text-right">{{ row.opening_qty }}</td>
              <td class="text-right text-success font-bold">+{{ row.inbound_qty
              }}</td>
              <td class="text-right text-danger font-bold">-{{ row.outbound_qty
              }}</td>
              <td class="text-right font-bold bg-[#f9f9f9]">{{ row.closing_qty }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onActivated, onMounted } from 'vue';
import axios from 'axios';
import * as XLSX from 'xlsx';
import { useToastStore } from '../../stores/toastStore';

const ledgerList = ref([]);
const toast = useToastStore();
const startDate = ref('');
const endDate = ref('');

const initDates = () => {
  const date = new Date();
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  startDate.value = `${year}-${month}-01`;
  endDate.value = date.toISOString().split('T')[0];
};

const fetchLedger = async () => {
  try {
    const res = await axios.get('/api/inventory/ledger/', {
      params: { start_date: startDate.value, end_date: endDate.value }
    });
    ledgerList.value = res.data;
  } catch (e) {
    console.error('수불부 조회 실패', e);
  }
};

const exportExcel = () => {
  if (ledgerList.value.length === 0) {
    toast.addToast('다운로드할 수불부 데이터가 없습니다.', 'error');
    return;
  }
  const excelData = ledgerList.value.map(row => ({
    '상품코드': row.sku,
    '상품명': row.name,
    '카테고리': row.category_name,
    '보관 위치': row.location,
    '기초재고': row.opening_qty,
    '당기입고': row.inbound_qty,
    '당기출고': row.outbound_qty,
    '기말재고': row.closing_qty
  }));

  const worksheet = XLSX.utils.json_to_sheet(excelData);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, '재고수불부');
  XLSX.writeFile(workbook, `재고수불부_${startDate.value}_to_${endDate.value}.xlsx`);
};

// 다른 탭에서 입출고한 뒤 돌아와도 최신 수치를 보여줍니다.
onMounted(initDates);
onActivated(fetchLedger);
</script>
<!-- CSS 삭제됨 -->