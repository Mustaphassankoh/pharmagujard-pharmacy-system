from django.urls import path

from . import views

app_name = 'clinical'

urlpatterns = [
    path('governance/', views.governance_dashboard, name='governance_dashboard'),
    path('governance/rules/', views.rule_report, name='rule_report'),
    path('governance/rules/export.csv', views.export_rules_csv, name='export_rules_csv'),
    path('governance/rules/<str:rule_type>/<int:pk>/history/', views.rule_history, name='rule_history'),
    path('governance/audits/', views.audit_report, name='audit_report'),
    path('governance/audits/export.csv', views.export_audits_csv, name='export_audits_csv'),
    path('governance/audits/<int:pk>/', views.audit_detail, name='audit_detail'),
]
