from django.urls import path

from . import views

app_name = 'clinical'

urlpatterns = [
    path('governance/', views.governance_dashboard, name='governance_dashboard'),
    path('governance/rules/manage/', views.rule_management, name='rule_management'),
    path('governance/allergens/add/', views.allergen_create, name='allergen_create'),
    path('governance/allergens/<int:pk>/edit/', views.allergen_update, name='allergen_update'),
    path('governance/rules/add/<str:rule_type>/', views.rule_create, name='rule_create'),
    path('governance/rules/', views.rule_report, name='rule_report'),
    path('governance/rules/export.csv', views.export_rules_csv, name='export_rules_csv'),
    path('governance/rules/<str:rule_type>/<int:pk>/history/', views.rule_history, name='rule_history'),
    path('governance/rules/<str:rule_type>/<int:pk>/<str:action>/', views.rule_lifecycle_action, name='rule_lifecycle_action'),
    path('governance/audits/', views.audit_report, name='audit_report'),
    path('governance/audits/export.csv', views.export_audits_csv, name='export_audits_csv'),
    path('governance/audits/<int:pk>/', views.audit_detail, name='audit_detail'),
]
