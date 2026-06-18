from django.urls import path
from .views import FuelRouteView

urlpatterns = [
    path('plan-route/', FuelRouteView.as_view(), name='plan_route'),
]