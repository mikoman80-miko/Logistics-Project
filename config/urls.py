from django.contrib import admin
from django.urls import path, include
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from inventory.serializers import RoleTokenObtainPairSerializer
from inventory.views import BadgeLoginView, CarrierWebhookView, PasswordChangeView


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
]
