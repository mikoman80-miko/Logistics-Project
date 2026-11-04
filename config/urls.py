from django.contrib import admin
from django.urls import include, path, re_path
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from inventory.serializers import RoleTokenObtainPairSerializer
from config import spa
from inventory.views import BadgeLoginView, CarrierWebhookView, HealthView, PasswordChangeView


class LoginView(TokenObtainPairView):
    serializer_class = RoleTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/inventory/', include('inventory.api_routes')),
    path('api/carrier/webhook/', CarrierWebhookView.as_view(), name='carrier_webhook'),
    path('api/account/password/', PasswordChangeView.as_view(), name='password_change'),
    path('api/token/', LoginView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/badge/', BadgeLoginView.as_view(), name='token_badge'),
    path('api/health/', HealthView.as_view(), name='health'),
    # 운영 모드: 그 밖의 주소는 화면(index.html)으로 보냅니다. (api/, admin/, static/ 은 제외)
    re_path(r'^(?!api/|admin/|static/).*$', spa.index, name='spa'),
]
