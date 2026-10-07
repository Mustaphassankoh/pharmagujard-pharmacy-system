"""
URL configuration for pharmacy_system project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from accounts import views as account_views
from . import views as system_views

admin.site.site_header = 'PharmaGuard Administration'
admin.site.site_title = 'PharmaGuard Admin'
admin.site.index_title = 'System Administration'

urlpatterns = [
    path('health/', system_views.health_check, name='health_check'),
    path('admin/', admin.site.urls),
    path('', account_views.home_view, name='home'),
    path('features/', account_views.features_view, name='features'),
    path('about/', account_views.about_view, name='about'),
    path('how-it-works/', account_views.how_it_works_view, name='how_it_works'),
    path('register/', account_views.register_pharmacy_view, name='register_pharmacy'),
    path('staff/', account_views.staff_list, name='staff_list'),
    path('staff/add/', account_views.staff_create, name='staff_create'),
    path('staff/<int:pk>/edit/', account_views.staff_update, name='staff_update'),
    path('staff/<int:pk>/deactivate/', account_views.staff_deactivate, name='staff_deactivate'),
    path('staff/<int:pk>/password/', account_views.staff_password, name='staff_password'),
    path('pharmacy-profile/', account_views.pharmacy_profile, name='pharmacy_profile'),
    path('dashboard/', account_views.dashboard_view, name='dashboard'),
    path('login/', auth_views.LoginView.as_view(template_name='accounts/login.html', redirect_authenticated_user=True), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('medicines/', include('medicines.urls', namespace='medicines')),
    path('inventory/', include('inventory.urls', namespace='inventory')),
    path('dispensing/', include('dispensing.urls', namespace='dispensing')),
    path('clinical/', include('clinical.urls', namespace='clinical')),
]

handler400 = 'pharmacy_system.views.error_400'
handler403 = 'pharmacy_system.views.error_403'
handler404 = 'pharmacy_system.views.error_404'
handler500 = 'pharmacy_system.views.error_500'
