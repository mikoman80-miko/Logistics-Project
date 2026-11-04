<template>
  <div class="flex flex-col gap-3 w-full h-full box-border">
    <!-- 상단 요약 지표 카드 (KPI Banner) -->
    <div class="panel">
      <table class="w-full border-collapse text-title">
        <tbody>
          <tr>
            <th class="border border-line p-2 text-center font-bold text-white bg-primary w-[15%]">총 등록 상품 (SKU)
            </th>
            <td class="border border-line px-3 py-2 text-right w-[10%] font-bold">{{ totalSkuCount.toLocaleString() }}
              건</td>
            <th class="border border-line p-2 text-center font-bold text-white bg-primary w-[15%]">창고 내 총 재고</th>
            <td class="border border-line px-3 py-2 text-right w-[10%] font-bold text-primary">{{
              totalQuantity.toLocaleString() }} 개</td>
            <th class="border border-line p-2 text-center font-bold text-white bg-danger-dark w-[15%]">재고 부족</th>
            <td class="border border-line px-3 py-2 text-right w-[10%] font-bold text-danger">{{
              lowStockCount.toLocaleString() }} SKU</td>
            <th class="border border-line p-2 text-center font-bold text-white bg-warning w-[15%]">오늘 입출고 건수</th>
            <td class="border border-line px-3 py-2 text-right w-[10%] font-bold text-warning">{{
              todayCount.toLocaleString() }} 건</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 장기 체화 재고 및 품절 경고 박스 -->
    <div v-if="lowStockItems.length > 0"
      class="border border-danger bg-danger-soft p-2 text-ink shadow-[2px_2px_0px_rgba(0,0,0,0.05)]">
      <div class="font-bold text-danger mb-1 text-body">※ 재고 부족 상품 (안전 재고 이하) - 발주가 필요한지 확인하세요</div>
      <div class="flex flex-wrap gap-1">
        <span v-for="item in lowStockItems" :key="item.id"
          class="bg-white border border-[#ffcdd2] px-1.5 py-0.5 text-caption">
          <span class="font-mono">[{{ item.sku }}]</span> {{ item.name }}
          <strong class="text-danger">({{ item.quantity }}개)</strong>
        </span>
      </div>
    </div>

    <!-- 대시보드 시각화 차트 영역 -->
    <div class="flex gap-3 h-[240px]">
      <div class="panel flex-1">
        <div class="panel-header panel-title">최근 30일 입출고 추이</div>
        <div class="p-2.5 h-full relative box-border overflow-hidden">
          <Bar v-if="isChartDataLoaded" :data="trendChartData" :options="chartOptions" />
          <div v-else class="text-center pt-[50px]">차트 데이터 로딩 중...</div>
        </div>
      </div>

      <div class="panel flex-1">
        <div class="panel-header panel-title">구역별 재고 비율</div>
        <div class="p-2.5 h-full relative box-border overflow-hidden">
          <Doughnut v-if="isChartDataLoaded" :data="occupancyChartData" :options="chartOptions" />
          <div v-else class="text-center pt-[50px]">차트 데이터 로딩 중...</div>
        </div>
      </div>
    </div>

    <!-- 중간 분석 그리드 영역 -->
    <div class="flex gap-3">
      <div class="panel flex-1">
        <div class="panel-header panel-title">보관 위치별 재고</div>
        <div class="p-2 overflow-auto h-[160px]">
          <table class="data-table data-table-sm">
            <thead>
              <tr>
                <th
                 
                  width="35%">보관 위치</th>
                <th
                 
                  width="35%">재고 수량</th>
                <th
                 
                  width="30%">비율(%)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="locationStats.length === 0">
                <td colspan="3" class="text-center">데이터 없음</td>
              </tr>
              <tr v-for="stat in locationStats" :key="stat.name">
                <td class="text-center">{{ stat.name || '미지정' }}</td>
                <td class="text-right font-bold">{{ stat.count.toLocaleString() }}
                </td>
                <td class="text-right">{{ stat.percent }}%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="panel flex-1">
        <div class="panel-header panel-title">입출고가 많은 상품 TOP 5 (최근 30일)</div>
        <div class="p-2 overflow-auto h-[160px]">
          <table class="data-table data-table-sm">
            <thead>
              <tr>
                <th
                 
                  width="15%">순위</th>
                <th
                 
                  width="30%">상품코드</th>
                <th
                 >
                  상품명</th>
                <th
                 
                  width="20%">변동 횟수</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="topMovingItems.length === 0">
                <td colspan="4" class="text-center">기록 없음</td>
              </tr>
              <tr v-for="(item, index) in topMovingItems" :key="item.sku">
                <td class="text-center font-bold">{{ index + 1 }}위</td>
                <td class="text-center font-mono">{{ item.sku }}</td>
                <td class="truncate">{{ item.name }}</td>
                <td class="text-right font-bold text-primary">{{ item.movements
                }}회</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 하단 전체 상세 내역 및 검색/엑셀 다운로드 -->
    <div class="panel flex-1 min-h-0">
      <div
        class="panel-header">
        <span class="panel-title">입출고 상세 기록</span>
        <div class="flex items-center">
            <span class="mr-2">총 <strong>{{ logTotal.toLocaleString() }}</strong>건 ({{ logPage }}/{{ logPageCount }})</span>
            <button class="btn btn-sm mr-0.5" :disabled="logPage <= 1" @click="logPage--">이전</button>
            <button class="btn btn-sm mr-2" :disabled="logPage >= logPageCount" @click="logPage++">다음</button>
          <select v-model="logFilter"
            class="field">
            <option value="ALL">전체 내역 보기</option>
            <option value="IN">입고 내역만</option>
            <option value="OUT">출고 내역만</option>
          </select>
          <input v-model="logSearch" type="text"
            class="field ml-1 w-[200px]"
            placeholder="상품명/SKU 검색" />
          <button @click="downloadCSV"
            class="btn btn-success ml-1">엑셀
            다운로드</button>
        </div>
      </div>
      <div class="p-0 flex-1 overflow-y-auto h-[220px]">
        <table class="data-table data-table-sm">
          <thead>
            <tr>
              <th
               
                width="180">발생 일시</th>
              <th
               
                width="100">구분</th>
              <th
               
                width="150">상품코드</th>
              <th
               >
                상품명</th>
              <th
               
                width="120">변동 수량</th>
              <th width="110">처리자</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="logRows.length === 0">
              <td colspan="6" class="text-center">조회된 입출고 내역이 없습니다.</td>
            </tr>
            <tr v-for="log in logRows" :key="log.id">
              <td class="text-center">{{ new
                Date(log.timestamp).toLocaleString('ko-KR') }}</td>
              <td class="text-center font-bold"
                :class="log.action === 'IN' ? 'text-success' : (log.action === 'OUT' ? 'text-primary' : 'text-warning')">
                {{ log.action_display || log.action }}
              </td>
              <td class="text-center font-mono">{{ log.item_sku }}</td>
              <td class="truncate">{{ log.item_name }}</td>
              <td class="text-right font-bold"
                :class="log.quantity_changed > 0 ? 'text-primary' : 'text-danger'">
                {{ log.quantity_changed > 0 ? '+' : '' }}{{ log.quantity_changed }}
              </td>
              <td class="text-center truncate">{{ log.user_name || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
// [기존 코드에서 단 1글자도 변경되지 않았습니다]
import { ref, computed, onActivated, watch } from 'vue';
import { useInventoryStore } from '../stores/inventory';
import axios from 'axios';
import { Bar, Doughnut } from 'vue-chartjs';
import { Chart as ChartJS, Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale, ArcElement } from 'chart.js';

ChartJS.register(Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale, ArcElement);

const store = useInventoryStore();
const logFilter = ref('ALL');
const logSearch = ref('');

const totalSkuCount = computed(() => store.items.length);
const totalQuantity = computed(() => store.items.reduce((sum, i) => sum + i.quantity, 0));
const lowStockCount = computed(() => store.items.filter(i => i.quantity <= i.safety_stock).length);
const lowStockItems = computed(() => store.items.filter(i => i.quantity <= i.safety_stock));

const todayCount = ref(0);
const topMovingItems = ref([]);

const locationStats = computed(() => {
  const stats = {};
  store.items.forEach(i => {
    const loc = i.location_name || '미지정';
    stats[loc] = (stats[loc] || 0) + i.quantity;
  });
  return Object.keys(stats).map(name => ({
    name,
    count: stats[name],
    percent: totalQuantity.value === 0 ? 0 : Math.round((stats[name] / totalQuantity.value) * 100)
  })).sort((a, b) => b.count - a.count);
});


const LOG_PAGE_SIZE = 50;
const logRows = ref([]);
const logTotal = ref(0);
const logPage = ref(1);
const logPageCount = computed(() => Math.max(1, Math.ceil(logTotal.value / LOG_PAGE_SIZE)));

const logParams = () => {
  const params = {};
  if (logFilter.value !== 'ALL') params.action = logFilter.value;
  if (logSearch.value.trim()) params.search = logSearch.value.trim();
  return params;
};

const loadLogs = async () => {
  const data = await store.fetchLogs({ ...logParams(), page: logPage.value, page_size: LOG_PAGE_SIZE });
  logRows.value = data.results;
  logTotal.value = data.count;
};

watch(logPage, loadLogs);

// 검색어 입력이 멈춘 뒤에 조회해 서버 요청을 줄입니다.
let searchTimer = null;
watch([logFilter, logSearch], () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    if (logPage.value === 1) loadLogs();
    else logPage.value = 1;
  }, 300);
});

const downloadCSV = () => store.downloadLogs(logParams());

const isChartDataLoaded = ref(false);
const trendChartData = ref({ labels: [], datasets: [] });
const occupancyChartData = ref({ labels: [], datasets: [] });
const chartOptions = { responsive: true, maintainAspectRatio: false };

const fetchChartData = async () => {
  try {
    const response = await axios.get('/api/inventory/dashboard/');
    const data = response.data;
    todayCount.value = data.today_count;
    topMovingItems.value = data.top_moving;

    trendChartData.value = {
      labels: data.trend.map(d => d.date),
      datasets: [
        { label: '입고 수량', backgroundColor: '#2e7d32', data: data.trend.map(d => d.inbound) },
        { label: '출고 수량', backgroundColor: '#00529b', data: data.trend.map(d => d.outbound) }
      ]
    };

    occupancyChartData.value = {
      labels: data.occupancy.map(d => `${d.zone}동`),
      datasets: [{
        backgroundColor: ['#00529b', '#e65100', '#2e7d32', '#d32f2f', '#607d8b'],
        data: data.occupancy.map(d => d.quantity)
      }]
    };
    isChartDataLoaded.value = true;
  } catch (error) {
    console.error('차트 데이터를 불러오지 못했습니다.', error);
  }
};

onActivated(() => {
  store.fetchItems();
  loadLogs();
  fetchChartData();
});
</script>
<!-- 🚨 기존의 <style scoped> 는 완벽히 제거되었습니다! 🚨 -->