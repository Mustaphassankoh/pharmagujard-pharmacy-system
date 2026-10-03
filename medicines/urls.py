from django.urls import path
from . import views

app_name = 'medicines'

urlpatterns = [
    # Medicine URLs
    path('', views.medicine_list, name='medicine_list'),
    path('add/', views.medicine_create, name='medicine_create'),
    path('<int:pk>/', views.medicine_detail, name='medicine_detail'),
    path('<int:pk>/edit/', views.medicine_update, name='medicine_update'),
    path('<int:pk>/toggle-status/', views.medicine_toggle_status, name='medicine_toggle_status'),

    # Category URLs
    path('categories/', views.category_list, name='category_list'),
    path('categories/add/', views.category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_update, name='category_update'),
    path('categories/<int:pk>/toggle-status/', views.category_toggle_status, name='category_toggle_status'),
]
