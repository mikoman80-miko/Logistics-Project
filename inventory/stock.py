"""위치별 재고 계산. 총재고(Item.quantity)를 바꾸는 곳에서 함께 불러 위치별 수량을 맞춥니다.

- 위치별 합은 총재고를 넘지 않습니다. 남는 수량은 '위치 미지정' 재고입니다.
- 넣을 때는 정한 위치(없으면 상품의 기본 위치)에, 꺼낼 때는 정한 위치 → 기본 위치 → 많은 곳 순서로 뺍니다.
- 위치에 없는 수량을 꺼내면 '위치 미지정' 재고에서 나간 것으로 봅니다.
"""

from django.db.models import F, Sum

from .models import ItemStock


def add(item, quantity, location=None):
    """quantity개를 location(없으면 기본 위치)에 넣습니다. 넣은 위치를 돌려줍니다. (위치가 없으면 미지정 재고)"""
    location = location or item.location
    if not location or quantity <= 0:
        return None
    row, _ = ItemStock.objects.select_for_update().get_or_create(item=item, location=location)
    ItemStock.objects.filter(pk=row.pk).update(quantity=F('quantity') + quantity)
    return location


def remove(item, quantity, prefer=None):
    """quantity개를 위치에서 뺍니다. 뺀 [(위치, 수량)]을 돌려줍니다. 모자라는 만큼은 미지정 재고에서 나간 것입니다."""
    rows = list(ItemStock.objects.select_for_update().filter(item=item, quantity__gt=0).select_related('location'))

    def order(row):
        return (0 if prefer and row.location_id == prefer.id else 1 if row.location_id == item.location_id else 2, -row.quantity)

    taken, left = [], quantity
    for row in sorted(rows, key=order):
        if left <= 0:
            break
        count = min(left, row.quantity)
        ItemStock.objects.filter(pk=row.pk).update(quantity=F('quantity') - count)
        taken.append((row.location, count))
        left -= count
    return taken


def at(item, location):
    row = ItemStock.objects.filter(item=item, location=location).first()
    return row.quantity if row else 0


def unassigned(item):
    located = ItemStock.objects.filter(item=item).aggregate(total=Sum('quantity'))['total'] or 0
    return max(0, item.quantity - located)


def move(item, quantity, source, target):
    """source(None이면 미지정 재고)에서 target으로 옮깁니다. 모자라면 오류 문구를 돌려줍니다."""
    available = at(item, source) if source else unassigned(item)
    if quantity > available:
        where = source.full_code if source else '위치 미지정'
        return f'{where}에 있는 재고가 {available}개라 {quantity}개를 옮길 수 없습니다.'
    if source:
        ItemStock.objects.filter(item=item, location=source).update(quantity=F('quantity') - quantity)
    add(item, quantity, target)
    return None


def set_at(item, location, quantity):
    """재고 조사: 이 위치의 수량을 quantity로 맞춥니다. 바뀐 양(+/-)을 돌려줍니다."""
    before = at(item, location)
    if quantity != before:
        row, _ = ItemStock.objects.select_for_update().get_or_create(item=item, location=location)
        ItemStock.objects.filter(pk=row.pk).update(quantity=quantity)
    return quantity - before


def relocate_one(item, source, target):
    """기기 1대가 기록과 다른 위치(target)에서 발견됐을 때 위치별 수량을 옮깁니다. 기록된 위치에 수량이 없으면 미지정 재고에서 옮깁니다."""
    if source and not move(item, 1, source, target):
        return
    move(item, 1, None, target)  # 미지정 재고에도 없으면 기록할 수량이 없으므로 그대로 둡니다.
