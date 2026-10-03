from django.urls import path
from . import views

app_name = 'dispensing'

urlpatterns = [
    # New Direct Sale — creates a DRAFT and redirects to cart
    path('new/', views.new_direct_sale, name='new_direct_sale'),

    # External Prescription workflow
    path('external/new/', views.new_external_prescription, name='new_external_prescription'),
    path('<int:pk>/external-cart/', views.external_prescription_cart, name='external_prescription_cart'),
    path('<int:pk>/external-add/', views.external_prescription_add_to_cart, name='external_prescription_add_to_cart'),
    path('<int:pk>/save-metadata/', views.external_prescription_save_metadata, name='external_prescription_save_metadata'),
    path('<int:pk>/confirm-external/', views.confirm_external_prescription, name='confirm_external_prescription'),

    # Consultation workflow
    path('consultation/new/', views.new_consultation, name='new_consultation'),
    path('<int:pk>/consultation-cart/', views.consultation_cart, name='consultation_cart'),
    path('<int:pk>/consultation-save-metadata/', views.consultation_save_metadata, name='consultation_save_metadata'),
    path('<int:pk>/confirm-consultation/', views.confirm_consultation, name='confirm_consultation'),
    path('<int:pk>/clinical-review/', views.run_clinical_review, name='run_clinical_review'),

    # Cart operations (all operate on a specific DRAFT transaction)
    path('<int:pk>/cart/', views.sale_cart, name='sale_cart'),
    path('<int:pk>/add/', views.add_to_cart, name='add_to_cart'),
    path('<int:pk>/remove/<int:medicine_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('<int:pk>/confirm/', views.confirm_sale, name='confirm_sale'),
    path('<int:pk>/cancel/', views.cancel_transaction, name='cancel_transaction'),

    # Transaction history & detail
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/<int:pk>/', views.transaction_detail, name='transaction_detail'),

    # Medicine search JSON endpoint (for cart autocomplete)
    path('api/medicines/', views.medicine_search_json, name='medicine_search_json'),
]
