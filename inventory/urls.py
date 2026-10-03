from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.inventory_list, name='inventory_list'),
    path('low-stock/', views.low_stock_list, name='low_stock_list'),
    path('expiry/', views.expiry_list, name='expiry_list'),
    path('batches/', views.batch_list, name='batch_list'),
    path('batches/add/', views.batch_create, name='batch_create'),
    path('batches/<int:pk>/', views.batch_detail, name='batch_detail'),
    path('batches/<int:pk>/edit/', views.batch_update, name='batch_update'),
    path('batches/<int:pk>/adjust/', views.batch_adjust, name='batch_adjust'),
    path('transactions/', views.transaction_list, name='transaction_list'),
]
