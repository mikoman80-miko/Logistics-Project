import { ref } from 'vue'
import { useWorkFeedback } from './useWorkFeedback'

// 현장 화면에서 보관 위치 라벨(LOC00012)을 스캔해 지금 품목의 자리가 맞는지 확인합니다.
export const isLocationCode = (code) => /^LOC\d{5}$/.test(code)

export const useLocationCheck = () => {
  const { ok, fail } = useWorkFeedback()
  const verified = ref([])  // 위치를 확인한 품목 줄 id

  // ending: 위치 뒤에 붙는 안내 ('에 보관합니다', '에서 꺼냅니다')
  const check = (code, line, ending = '에 보관합니다') => {
    if (!line) return fail('먼저 상품 바코드를 스캔하세요. 그다음 위치 라벨을 스캔하면 맞는 자리인지 확인합니다.')
    if (!line.location_barcode) return fail(`[${line.item_name}] 보관 위치가 지정되지 않은 상품입니다. 관리자에게 위치 지정을 요청하세요.`)
    if (code !== line.location_barcode) return fail(`다른 위치입니다. 이 상품은 ${line.location_name}${ending}.`)
    if (!verified.value.includes(line.id)) verified.value.push(line.id)
    ok(`위치 확인: ${line.location_name}`)
  }
  const isVerified = (line) => !!line && verified.value.includes(line.id)
  const reset = () => { verified.value = [] }

  return { check, isVerified, reset }
}
