// 집품 리스트: 여러 주문의 남은 품목을 상품별로 합치고, 재고가 있는 위치에 나눠 위치 순서로 정렬합니다.
// 위치 배분: 기본 위치 → 재고 많은 위치 순으로 채우고, 모자라면 기본 위치(없으면 '위치 미지정')에서 꺼내도록 안내합니다.
export const buildPickList = (orders) => {
  const byItem = new Map()
  for (const order of orders) {
    for (const line of order.items) {
      const need = line.quantity - line.picked_quantity
      if (need <= 0) continue
      if (!byItem.has(line.item)) {
        byItem.set(line.item, {
          item: line.item, sku: line.item_sku, name: line.item_name, serial_tracked: line.serial_tracked,
          places: line.stock_locations, fallback: { location_name: line.location_name || '위치 미지정', barcode: line.location_barcode || '' },
          total: 0, orders: [],
        })
      }
      const entry = byItem.get(line.item)
      entry.total += need
      entry.orders.push({ order_no: order.order_no, customer: order.customer, quantity: need })
    }
  }

  const rows = []
  for (const entry of byItem.values()) {
    let left = entry.total
    for (const place of entry.places) {
      if (left <= 0) break
      const take = Math.min(left, place.quantity)
      rows.push({ ...entry, key: `${entry.item}-${place.barcode}`, location_name: place.location_name, barcode: place.barcode, quantity: take })
      left -= take
    }
    if (left > 0) rows.push({ ...entry, key: `${entry.item}-rest`, ...entry.fallback, quantity: left, short: entry.places.length > 0 })
  }
  return rows.sort((a, b) => a.location_name.localeCompare(b.location_name) || a.name.localeCompare(b.name))
}
