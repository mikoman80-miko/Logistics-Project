"""기준정보 변경 이력: 상품·위치·거래처·카테고리·사용자를 누가 언제 어떻게 바꿨는지 남깁니다.

재고 수량 변화는 입출고 이력(InventoryLog)에 남으므로 여기서는 기준정보 칸만 비교합니다.
"""
from django.contrib.auth.models import User

from .models import Category, Item, MasterChange, Supplier, WarehouseLocation

# 모델별로 기록할 칸과 화면에 보일 이름
FIELDS = {
    Item: ('상품', {
        'sku': '상품코드', 'name': '상품명', 'item_type': '구분', 'serial_tracked': '시리얼 관리', 'category': '카테고리',
        'location': '기본 위치', 'safety_stock': '안전 재고', 'pick_min': '보충 최소', 'pick_max': '보충 최대', 'is_active': '사용',
    }),
    WarehouseLocation: ('위치', {'zone': '구역', 'rack': '랙', 'tier': '단', 'cell': '칸', 'description': '설명', 'is_active': '사용'}),
    Supplier: ('거래처', {'name': '거래처명', 'contact_person': '담당자', 'phone': '연락처', 'email': '이메일', 'is_active': '사용'}),
    Category: ('카테고리', {'name': '이름', 'parent': '상위', 'description': '설명'}),
    User: ('사용자', {'username': '사원번호', 'first_name': '이름', 'is_staff': '관리자 권한', 'is_active': '사용'}),
}


def display(value):
    if value is None or value == '':
        return ''
    if isinstance(value, bool):
        return '예' if value else '아니오'
    return str(value)


def snapshot(obj):
    """기록할 칸의 지금 값 (화면에 보이는 글자로)"""
    _, fields = FIELDS[type(obj)]
    return {label: display(getattr(obj, name)) for name, label in fields.items()}


def label_of(obj):
    if isinstance(obj, Item):
        return f'{obj.sku} {obj.name}'
    if isinstance(obj, WarehouseLocation):
        return obj.full_code
    if isinstance(obj, User):
        return f'{obj.username} {obj.first_name}'.strip()
    return str(obj)


def record(user, obj, action, before=None, after=None):
    """변경 이력 한 줄. 수정은 바뀐 칸만, 등록은 값이 있는 칸만 남깁니다. 바뀐 것이 없으면 남기지 않습니다."""
    target, _ = FIELDS[type(obj)]
    after = snapshot(obj) if after is None else after
    if before is None:
        changes = {key: ['', value] for key, value in after.items() if value not in ('', '아니오')}
    else:
        changes = {key: [before.get(key, ''), value] for key, value in after.items() if before.get(key, '') != value}
        if not changes and action == '수정':
            return None
    return MasterChange.objects.create(target=target, object_id=obj.pk, label=label_of(obj)[:200], action=action, changes=changes,
                                       user=user if user and user.is_authenticated else None)


class AuditMixin:
    """ModelViewSet에 섞어 등록·수정·삭제 요청을 자동으로 기록합니다.
    (뷰셋마다 perform_* 를 따로 고쳐 쓰므로, 그 바깥인 create/update/destroy에서 앞뒤 값을 비교합니다.)"""

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code == 201:
            obj = self.get_queryset().model.objects.get(pk=response.data['id'])
            record(request.user, obj, '등록')
        return response

    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        before = snapshot(obj)
        response = super().update(request, *args, **kwargs)
        obj.refresh_from_db()
        record(request.user, obj, '수정', before)
        return response

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        before, model, pk = snapshot(obj), type(obj), obj.pk
        response = super().destroy(request, *args, **kwargs)
        still = model.objects.filter(pk=pk).first()  # 상품처럼 지우지 않고 사용 중지하는 경우
        if still:
            record(request.user, still, '사용 중지', before)
        else:
            obj.pk = pk
            record(request.user, obj, '삭제', before, after={key: '' for key in before})
        return response
