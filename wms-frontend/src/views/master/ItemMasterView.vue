<template>
  <div class="page">
    <div class="panel p-1.5">
      <table class="form-table">
        <tbody>
          <tr>
            <th>상품명/코드 검색</th>
            <td><input v-model="searchQuery" type="text"
                class="field w-full"
                placeholder="상품명 또는 상품코드 검색" /></td>
            <th>카테고리 필터</th>
            <td>
              <select v-model="selectedCategory"
                class="field w-full">
                <option value="전체">전체 카테고리</option>
                <option v-for="cat in categories" :key="cat.id" :value="cat.name">{{ cat.name }}</option>
              </select>
            </td>
            <td class="text-right">
              <button
                class="btn btn-primary"
                @click="fetchItems">새로고침</button>
            </td>
          </tr>
          <tr>
            <th>상품 수동 등록</th>
            <td colspan="4">
              <form @submit.prevent="handleAddItem" class="flex flex-wrap items-center gap-1.5">
                구분: <select v-model="newItemForm.item_type" class="field w-[80px]" @change="newItemForm.serial_tracked = newItemForm.item_type === '상품'">
                  <option v-for="type in ITEM_TYPES" :key="type" :value="type">{{ type }}</option>
                </select>
                <label class="flex items-center gap-1"><input v-model="newItemForm.serial_tracked" type="checkbox" /> 시리얼 관리</label>
                상품코드: <input v-model="newItemForm.sku"
                  class="field w-[120px]" required
                  placeholder="상품코드 입력" />
                상품명: <input v-model="newItemForm.name"
                  class="field w-[180px]" required
                  placeholder="상품명 입력" />
                카테고리: <select v-model="newItemForm.category" class="field w-[120px]">
                  <option :value="null">미분류</option>
                  <option v-for="cat in categories" :key="cat.id" :value="cat.id">{{ cat.name }}</option>
                </select>
                <button type="button" class="btn" @click="addCategory">추가</button>
                수량: <input type="number" v-model="newItemForm.quantity"
                  class="field field-num w-[60px]" min="0" required />
                안전 재고: <input type="number" v-model.number="newItemForm.safety_stock"
                  class="field field-num w-[60px]" min="0" required />
                <button type="submit"
                  class="btn btn-success ml-2">신규
                  등록</button>

                <input type="file" ref="csvInput" accept=".csv" class="hidden" @change="handleCsvUpload" />
                <button type="button" @click="$refs.csvInput.click()"
                  class="btn btn-warning ml-1">CSV
                  일괄 업로드</button>
                <!-- 🌟 NEW: ABC 분석 실행 버튼 -->
                <button type="button" @click="runABCAnalysis"
                  class="btn btn-primary ml-1">ABC
                  분석 실행</button>
              </form>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div
      class="panel flex-1 overflow-hidden mt-2.5">
      <div class="panel-header">
        <span class="panel-title">상품 목록</span>
        <span class="text-body">총 <strong>{{ filteredItems.length }}</strong> 개 상품</span>
      </div>

      <div class="panel-body-flush">
        <table class="data-table">
          <thead>
            <tr>
              <th width="90">구분</th>
              <th width="70">시리얼</th>
              <th width="120">상품코드</th>
              <th
               >
                상품명</th>
              <th
               
                width="150">카테고리</th>
              <!-- 🌟 NEW: ABC 등급 표시 컬럼 -->
              <th
                class="text-primary"
                width="60">ABC</th>
              <th width="80">현재수량</th>
              <th width="80">안전 재고</th>
              <th
               
                width="180">보관 위치</th>
              <th width="170">관리 도구</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="filteredItems.length === 0">
              <td colspan="10" class="text-center text-gray-500 font-bold">조회된 상품이 없습니다. 위에서 상품을 등록하세요.</td>
            </tr>
            <tr v-for="item in filteredItems" :key="item.id">
              <td class="text-center">
                <select class="field field-sm w-full" :value="item.item_type" @change="changeItem(item, { item_type: $event.target.value, serial_tracked: $event.target.value === '상품' })">
                  <option v-for="type in ITEM_TYPES" :key="type" :value="type">{{ type }}</option>
                </select>
              </td>
              <td class="text-center">
                <input type="checkbox" :checked="item.serial_tracked" @change="changeItem(item, { serial_tracked: $event.target.checked })" />
              </td>
              <td class="text-center font-mono font-bold">{{ item.sku }}</td>
              <td class="font-bold">{{ item.name }}</td>
              <td class="text-center">{{ getCategoryName(item.category) }}</td>
              <!-- 🌟 NEW: ABC 등급 데이터 -->
              <td class="text-center font-bold"
                :class="{ 'text-danger': item.abc_grade === 'C', 'text-success': item.abc_grade === 'A' }">{{
                  item.abc_grade || '-' }}</td>
              <td class="text-right font-bold"
                :class="{ 'text-danger': item.quantity === 0, 'text-warning': item.quantity > 0 && item.quantity <= item.safety_stock }">{{ item.quantity.toLocaleString() }}</td>
              <td class="text-right">{{ item.safety_stock }}</td>
              <td class="text-center font-mono">{{ getLocationName(item.location) }}
              </td>
              <td class="text-center flex justify-center gap-1">
                <button class="btn btn-sm" @click="openEditModal(item)">수정</button>
                <button
                  class="btn btn-success btn-sm"
                  @click="openTransferModal(item)">위치이동</button>
                <button
                  class="btn btn-danger btn-sm"
                  @click="deleteItem(item.id)">삭제</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 상품 수정 모달 -->
    <div v-if="editForm" class="modal-overlay" @click.self="editForm = null">
      <form class="modal w-[450px]" @submit.prevent="submitEdit">
        <div class="modal-header">상품 수정 <span class="font-mono">({{ editForm.sku }})</span></div>
        <div class="modal-content flex flex-col gap-2.5">
          <label class="field-label">상품명
            <input v-model="editForm.name" class="field w-full mt-1" maxlength="200" required />
          </label>
          <label class="field-label">카테고리
            <select v-model="editForm.category" class="field w-full mt-1">
              <option :value="null">미분류</option>
              <option v-for="cat in categories" :key="cat.id" :value="cat.id">{{ cat.name }}</option>
            </select>
          </label>
          <label class="field-label">안전 재고
            <input v-model.number="editForm.safety_stock" type="number" min="0" class="field field-num w-[120px] mt-1 block" required />
            <span class="block mt-1 font-normal text-muted">현재 재고가 이 수량 이하이면 재고 부족으로 표시하고 알림을 보냅니다.</span>
          </label>
        </div>
        <div class="modal-footer">
          <button type="submit" class="btn btn-primary btn-lg">저장</button>
          <button type="button" class="btn btn-lg" @click="editForm = null">취소</button>
        </div>
      </form>
    </div>

    <!-- 보관 위치 이동 모달 -->
    <div v-if="isTransferModalOpen" class="modal-overlay"
      @click.self="closeTransferModal">
      <div class="modal w-[450px]">
        <div class="modal-header">보관 위치 이동</div>
        <div class="modal-content">
          <div class="bg-[#eff6ff] border border-[#bfdbfe] text-[#1e40af] p-3 mb-4 text-sm font-bold">대상 상품: {{
            selectedItem?.name }} <span class="font-mono">({{ selectedItem?.sku }})</span></div>
          <div class="flex flex-col gap-2">
            <label class="font-bold text-[#374151] text-xs">이동할 목표 보관 위치 선택</label>
            <select v-model="selectedLocationId"
              class="field field-lg">
              <option value="" disabled>== 창고 구역 선택 ==</option>
              <option v-for="loc in locations" :key="loc.id" :value="loc.id">{{ loc.zone }}동 - {{ loc.rack }}열 - {{
                loc.tier }}단 {{ loc.cell ? '(' + loc.cell + ')' : '' }}</option>
            </select>
          </div>
        </div>
        <div class="modal-footer">
          <button @click="submitTransfer"
            class="btn btn-primary btn-lg"
            :disabled="!selectedLocationId">이동 확정</button>
          <button @click="closeTransferModal"
            class="btn btn-lg">취소</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onActivated } from 'vue';
import axios from 'axios';
import { useToastStore } from '../../stores/toastStore';
import { apiErrorMessage } from '../../utils/apiError';
import { useDialogStore } from '../../stores/dialogStore';

const items = ref([]);
const locations = ref([]);
const categories = ref([]);
const searchQuery = ref('');
const selectedCategory = ref('전체');

const isTransferModalOpen = ref(false);
const selectedItem = ref(null);
const selectedLocationId = ref('');
const ITEM_TYPES = ['상품', '구성품', '부자재', '사은품'];
const emptyItemForm = () => ({ item_type: '상품', serial_tracked: true, sku: '', name: '', quantity: 0, safety_stock: 5, category: null });
const newItemForm = ref(emptyItemForm());
const toast = useToastStore();
const dialog = useDialogStore();
const csvInput = ref(null);

const fetchItems = async () => {
  try {
    const res = await axios.get('/api/inventory/items/');
    items.value = res.data;
  } catch (err) { console.error(err); }
};

const fetchLocations = async () => {
  try {
    const res = await axios.get('/api/inventory/locations/');
    locations.value = res.data;
  } catch (err) { console.error(err); }
};

const fetchCategories = async () => {
  try {
    const res = await axios.get('/api/inventory/categories/');
    categories.value = res.data;
  } catch (err) { console.error(err); }
};

const filteredItems = computed(() => {
  return items.value.filter(item => {
    const matchQuery = item.name.toLowerCase().includes(searchQuery.value.toLowerCase()) || item.sku.toLowerCase().includes(searchQuery.value.toLowerCase());
    const catName = getCategoryName(item.category);
    const matchCat = selectedCategory.value === '전체' || catName === selectedCategory.value;
    return matchQuery && matchCat;
  });
});

const getCategoryName = (catId) => {
  if (!catId) return '미분류';
  const cat = categories.value.find(c => c.id === catId);
  return cat ? cat.name : '미분류';
};

const getLocationName = (locId) => {
  if (!locId) return '미지정';
  const loc = locations.value.find(l => l.id === locId);
  if (loc) return loc.cell ? `${loc.zone}-${loc.rack}-${loc.tier}단-${loc.cell}` : `${loc.zone}-${loc.rack}-${loc.tier}단`;
  return '미지정';
};

const changeItem = async (item, change) => {
  try {
    await axios.patch(`/api/inventory/items/${item.id}/`, change);
    toast.addToast(`[${item.sku}] 변경되었습니다.`, 'success');
  } catch (err) {
    toast.addToast(apiErrorMessage(err, '변경 중 오류가 발생했습니다.'), 'error', 5000);
  }
  await fetchItems();
};

const addCategory = async () => {
  const name = await dialog.prompt('새 카테고리 이름을 입력하세요.', { title: '카테고리 추가', okText: '추가', maxlength: 100 });
  if (!name) return;
  try {
    const res = await axios.post('/api/inventory/categories/', { name });
    await fetchCategories();
    newItemForm.value.category = res.data.id;
  } catch (err) { toast.addToast(apiErrorMessage(err, '카테고리 추가 중 오류가 발생했습니다.'), 'error'); }
};

const handleAddItem = async () => {
  try {
    await axios.post('/api/inventory/items/', newItemForm.value);
    toast.addToast('상품이 신규 등록되었습니다.', 'success');
    newItemForm.value = emptyItemForm();
    await fetchItems();
  } catch (err) { toast.addToast(apiErrorMessage(err, '등록 실패 (SKU 중복 확인)'), 'error'); }
};

const deleteItem = async (id) => {
  if (!(await dialog.confirm('이 상품을 삭제하시겠습니까?\n입출고 이력은 남고 목록에서만 사라집니다.', { danger: true, okText: '삭제' }))) return;
  try {
    await axios.delete(`/api/inventory/items/${id}/`);
    toast.addToast('상품이 삭제되었습니다.', 'success');
    await fetchItems();
  } catch (err) { toast.addToast(apiErrorMessage(err, '삭제 중 오류가 발생했습니다.'), 'error', 5000); }
};

const editForm = ref(null);
const openEditModal = (item) => {
  editForm.value = { id: item.id, sku: item.sku, name: item.name, category: item.category, safety_stock: item.safety_stock };
};
const submitEdit = async () => {
  const { id, sku, ...change } = editForm.value;
  try {
    await axios.patch(`/api/inventory/items/${id}/`, change);
    toast.addToast(`[${sku}] 수정되었습니다.`, 'success');
    editForm.value = null;
    await fetchItems();
  } catch (err) { toast.addToast(apiErrorMessage(err, '수정 중 오류가 발생했습니다.'), 'error', 5000); }
};

const openTransferModal = (item) => {
  selectedItem.value = item;
  selectedLocationId.value = '';
  isTransferModalOpen.value = true;
};

const closeTransferModal = () => {
  isTransferModalOpen.value = false;
  selectedItem.value = null;
  selectedLocationId.value = '';
};

const submitTransfer = async () => {
  if (!selectedLocationId.value) return;
  try {
    await axios.post(`/api/inventory/items/${selectedItem.value.id}/transfer_location/`, { new_location_id: selectedLocationId.value });
    toast.addToast('보관 위치 이동이 완료되었습니다.', 'success');
    closeTransferModal();
    await fetchItems();
  } catch (err) { toast.addToast(apiErrorMessage(err, '이동 중 오류가 발생했습니다.'), 'error', 5000); }
};

const handleCsvUpload = async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await axios.post('/api/inventory/items/upload_csv/', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
    toast.addToast(res.data.message, 'success');
    await fetchItems();
  } catch (err) {
    toast.addToast(err.response?.data?.error || 'CSV 업로드 중 오류가 발생했습니다.', 'error');
  } finally { event.target.value = ''; }
};

// 🌟 NEW: 백엔드 ABC 분석 API 호출 함수
const runABCAnalysis = async () => {
  try {
    const res = await axios.post('/api/inventory/items/analyze_abc/');
    toast.addToast(res.data.message, 'success');
    await fetchItems(); // 분석 후 테이블 갱신
  } catch (err) {
    toast.addToast('ABC 분석 중 오류가 발생했습니다.', 'error');
  }
};

onActivated(async () => {
  await Promise.all([fetchItems(), fetchLocations(), fetchCategories()]);
});
</script>