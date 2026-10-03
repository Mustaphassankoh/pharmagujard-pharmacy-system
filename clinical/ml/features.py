from clinical.models import AlertTypeChoices, ClinicalCheckStatus

FEATURES = ['medicine_count','interaction_warning_count','allergy_warning_count','dosage_warning_count','low_alert_count','moderate_alert_count','high_alert_count','critical_alert_count','not_checked_count','warning_check_count','transaction_type']
TRANSACTION_TYPES = {'DIRECT_SALE': 0, 'EXTERNAL_PRESCRIPTION': 1, 'CONSULTATION': 2}

def extract_review_features(transaction):
    alerts = list(transaction.clinical_alerts.all())
    results = list(transaction.clinical_check_results.all())
    review = getattr(transaction, 'clinical_review', None)
    fingerprint_count = len([value for value in (review.medicine_fingerprint.split(',') if review else []) if value])
    return {
        'medicine_count': len(set(transaction.items.values_list('medicine_id', flat=True))) or fingerprint_count,
        'interaction_warning_count': sum(a.alert_type == AlertTypeChoices.DRUG_INTERACTION for a in alerts),
        'allergy_warning_count': sum(a.alert_type == AlertTypeChoices.ALLERGY for a in alerts),
        'dosage_warning_count': sum(a.alert_type == AlertTypeChoices.DOSAGE for a in alerts),
        'low_alert_count': sum(a.severity == 'LOW' for a in alerts),
        'moderate_alert_count': sum(a.severity == 'MODERATE' for a in alerts),
        'high_alert_count': sum(a.severity == 'HIGH' for a in alerts),
        'critical_alert_count': sum(a.severity == 'CRITICAL' for a in alerts),
        'not_checked_count': sum(r.status == ClinicalCheckStatus.NOT_CHECKED for r in results),
        'warning_check_count': sum(r.status == ClinicalCheckStatus.WARNING for r in results),
        'transaction_type': TRANSACTION_TYPES[transaction.transaction_type],
    }
