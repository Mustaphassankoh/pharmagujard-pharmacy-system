from itertools import combinations

from django.db import transaction
from django.utils import timezone

from dispensing.models import TransactionStatusChoices, TransactionTypeChoices
from medicines.models import Medicine

from .models import (
    AlertTypeChoices,
    AllergyRule,
    ClinicalAlert,
    ClinicalCheckResult,
    ClinicalCheckStatus,
    ClinicalCheckType,
    ClinicalReview,
    DrugInteractionRule,
)
from .dosage import check_dosage, dosage_fingerprint
from .governance import effective_rules


def _medicine_ids(clinical_input):
    return clinical_input.keys() if isinstance(clinical_input, dict) else clinical_input


def medicine_fingerprint(medicine_ids):
    return ','.join(str(pk) for pk in sorted({int(pk) for pk in medicine_ids}))


def allergy_fingerprint(dispensing_transaction, medicine_ids):
    medicine_part = medicine_fingerprint(medicine_ids)
    allergen_ids = []
    if dispensing_transaction.transaction_type == TransactionTypeChoices.CONSULTATION:
        consultation = getattr(dispensing_transaction, 'consultation', None)
        if consultation:
            allergen_ids = list(consultation.structured_allergies.values_list('pk', flat=True))
    allergen_part = ','.join(str(pk) for pk in sorted(allergen_ids))
    return f'medicines:{medicine_part}|allergens:{allergen_part}'


def _derive_overall_status(results):
    """Derive the summary without treating unavailable allergy context as a failure."""
    if any(result.details.get('execution_failed') for result in results):
        return ClinicalCheckStatus.NOT_CHECKED
    if any(result.status == ClinicalCheckStatus.WARNING for result in results):
        return ClinicalCheckStatus.WARNING
    applicable_results = [result for result in results if not result.details.get('context_unavailable')]
    if any(result.status == ClinicalCheckStatus.PASSED for result in applicable_results):
        return ClinicalCheckStatus.PASSED
    if applicable_results and all(result.status == ClinicalCheckStatus.NOT_APPLICABLE for result in applicable_results):
        return ClinicalCheckStatus.NOT_APPLICABLE
    return ClinicalCheckStatus.NOT_CHECKED


def _sync_review(dispensing_transaction, medicine_ids):
    results = list(ClinicalCheckResult.objects.filter(transaction=dispensing_transaction))
    review, _ = ClinicalReview.objects.get_or_create(transaction=dispensing_transaction)
    interaction = next((r for r in results if r.check_type == ClinicalCheckType.DRUG_INTERACTION), None)
    review.status = _derive_overall_status(results)
    review.medicine_fingerprint = medicine_fingerprint(medicine_ids)
    review.checked_pairs = (interaction.details or {}).get('checked_pairs', 0) if interaction else 0
    checked_times = [result.checked_at for result in results if result.checked_at]
    review.checked_at = max(checked_times) if checked_times else None
    review.save()
    return review


@transaction.atomic
def check_drug_interactions(dispensing_transaction, medicine_ids):
    ids = sorted({int(pk) for pk in medicine_ids})
    fingerprint = medicine_fingerprint(ids)
    result_row, _ = ClinicalCheckResult.objects.select_for_update().get_or_create(
        transaction=dispensing_transaction,
        check_type=ClinicalCheckType.DRUG_INTERACTION,
    )

    if dispensing_transaction.status != TransactionStatusChoices.DRAFT:
        alerts = list(dispensing_transaction.clinical_alerts.filter(alert_type=AlertTypeChoices.DRUG_INTERACTION))
        return {'status': result_row.status, 'alerts': alerts, 'checked_pairs': result_row.details.get('checked_pairs', 0)}

    ClinicalAlert.objects.filter(
        transaction=dispensing_transaction,
        alert_type=AlertTypeChoices.DRUG_INTERACTION,
    ).delete()
    medicines = {medicine.pk: medicine for medicine in Medicine.objects.filter(pk__in=ids)}
    now = timezone.now()
    if len(medicines) != len(ids):
        status = ClinicalCheckStatus.NOT_CHECKED
        pairs = []
        alerts = []
        details = {'checked_pairs': 0, 'execution_failed': True, 'reason': 'One or more selected medicines could not be resolved.'}
    else:
        pairs = list(combinations(ids, 2))
        alerts = []
        details = {'checked_pairs': len(pairs), 'execution_failed': False}
        if not pairs:
            status = ClinicalCheckStatus.NOT_APPLICABLE
            details['reason'] = 'Fewer than two distinct medicines were selected.'
        else:
            pair_set = set(pairs)
            rules = effective_rules(DrugInteractionRule.objects.filter(
                medicine_a_id__in=ids,
                medicine_b_id__in=ids,
            )).select_related('medicine_a', 'medicine_b')
            for rule in rules:
                if (rule.medicine_a_id, rule.medicine_b_id) not in pair_set:
                    continue
                alerts.append(ClinicalAlert.objects.create(
                    transaction=dispensing_transaction,
                    alert_type=AlertTypeChoices.DRUG_INTERACTION,
                    severity=rule.severity,
                    status=ClinicalCheckStatus.WARNING,
                    medicine_a=rule.medicine_a,
                    medicine_b=rule.medicine_b,
                    title=f'Drug interaction: {rule.medicine_a.generic_name} + {rule.medicine_b.generic_name}',
                    description=rule.description,
                    explanation=rule.explanation,
                    recommendation=rule.recommendation,
                    source_reference=rule.source_reference,
                    rule_reference=rule,
                    snapshot_details={'rule_version': rule.version},
                ))
            status = ClinicalCheckStatus.WARNING if alerts else ClinicalCheckStatus.PASSED

    result_row.status = status
    result_row.input_fingerprint = fingerprint
    result_row.checked_at = now
    result_row.details = details
    result_row.save()
    _sync_review(dispensing_transaction, ids)
    return {'status': status, 'alerts': alerts, 'checked_pairs': len(pairs)}


@transaction.atomic
def check_allergies(dispensing_transaction, medicine_ids):
    ids = sorted({int(pk) for pk in medicine_ids})
    fingerprint = allergy_fingerprint(dispensing_transaction, ids)
    result_row, _ = ClinicalCheckResult.objects.select_for_update().get_or_create(
        transaction=dispensing_transaction,
        check_type=ClinicalCheckType.ALLERGY,
    )

    if dispensing_transaction.status != TransactionStatusChoices.DRAFT:
        alerts = list(dispensing_transaction.clinical_alerts.filter(alert_type=AlertTypeChoices.ALLERGY))
        return {'status': result_row.status, 'alerts': alerts, 'details': result_row.details}

    ClinicalAlert.objects.filter(
        transaction=dispensing_transaction,
        alert_type=AlertTypeChoices.ALLERGY,
    ).delete()
    now = timezone.now()
    medicines = {medicine.pk: medicine for medicine in Medicine.objects.filter(pk__in=ids)}
    consultation = None
    allergen_ids = []
    if dispensing_transaction.transaction_type == TransactionTypeChoices.CONSULTATION:
        consultation = getattr(dispensing_transaction, 'consultation', None)
        if consultation:
            allergen_ids = list(consultation.structured_allergies.values_list('pk', flat=True))

    alerts = []
    if len(medicines) != len(ids):
        status = ClinicalCheckStatus.NOT_CHECKED
        details = {'execution_failed': True, 'reason': 'One or more selected medicines could not be resolved.'}
    elif dispensing_transaction.transaction_type != TransactionTypeChoices.CONSULTATION:
        status = ClinicalCheckStatus.NOT_CHECKED
        details = {'execution_failed': False, 'context_unavailable': True, 'reason': 'No structured allergy information was available for automated checking.'}
    elif not consultation or not allergen_ids:
        status = ClinicalCheckStatus.NOT_CHECKED
        details = {'execution_failed': False, 'context_unavailable': True, 'reason': 'No structured allergy information was available for automated checking.'}
    else:
        rules = effective_rules(AllergyRule.objects.filter(
            medicine_id__in=ids,
            allergen_id__in=allergen_ids,
        )).select_related('medicine', 'allergen')
        for rule in rules:
            alerts.append(ClinicalAlert.objects.create(
                transaction=dispensing_transaction,
                alert_type=AlertTypeChoices.ALLERGY,
                severity=rule.severity,
                status=ClinicalCheckStatus.WARNING,
                medicine_a=rule.medicine,
                allergen=rule.allergen,
                title=f'Allergy warning: {rule.allergen.name} + {rule.medicine.generic_name}',
                description=rule.description,
                explanation=rule.explanation,
                recommendation=rule.recommendation,
                source_reference=rule.source_reference,
                allergy_rule_reference=rule,
                snapshot_details={'rule_version': rule.version},
            ))
        status = ClinicalCheckStatus.WARNING if alerts else ClinicalCheckStatus.PASSED
        details = {'execution_failed': False, 'structured_allergen_count': len(allergen_ids)}

    result_row.status = status
    result_row.input_fingerprint = fingerprint
    result_row.checked_at = now
    result_row.details = details
    result_row.save()
    _sync_review(dispensing_transaction, ids)
    return {'status': status, 'alerts': alerts, 'details': details}


@transaction.atomic
def run_clinical_review(dispensing_transaction, clinical_input):
    ids = sorted({int(pk) for pk in _medicine_ids(clinical_input)})
    interaction = check_drug_interactions(dispensing_transaction, ids)
    allergy = check_allergies(dispensing_transaction, ids)
    dosage = check_dosage(dispensing_transaction, clinical_input)
    review = _sync_review(dispensing_transaction, ids)
    from .ml.predictor import predict_review_priority
    ml_priority = predict_review_priority(dispensing_transaction)
    return {
        'status': review.status,
        'review': review,
        'interaction': interaction,
        'allergy': allergy,
        'dosage': dosage,
        'ml_priority': ml_priority,
        'alerts': list(dispensing_transaction.clinical_alerts.select_related('medicine_a', 'medicine_b', 'allergen')),
    }


def current_review(dispensing_transaction, clinical_input):
    medicine_ids = _medicine_ids(clinical_input)
    try:
        review = dispensing_transaction.clinical_review
    except ClinicalReview.DoesNotExist:
        return None
    if review.medicine_fingerprint != medicine_fingerprint(medicine_ids):
        return None
    allergy_result = dispensing_transaction.clinical_check_results.filter(check_type=ClinicalCheckType.ALLERGY).first()
    if allergy_result and allergy_result.input_fingerprint != allergy_fingerprint(dispensing_transaction, medicine_ids):
        return None
    dosage_result = dispensing_transaction.clinical_check_results.filter(check_type=ClinicalCheckType.DOSAGE).first()
    if not dosage_result or dosage_result.input_fingerprint != dosage_fingerprint(dispensing_transaction, clinical_input):
        return None
    return review


def invalidate_clinical_review(dispensing_transaction):
    ClinicalReview.objects.filter(transaction=dispensing_transaction).update(
        status=ClinicalCheckStatus.NOT_CHECKED,
        medicine_fingerprint='',
        checked_pairs=0,
        checked_at=None,
    )
    ClinicalCheckResult.objects.filter(transaction=dispensing_transaction).delete()
    ClinicalAlert.objects.filter(transaction=dispensing_transaction).delete()
    if dispensing_transaction.status == TransactionStatusChoices.DRAFT:
        from .models import ClinicalRiskAssessment
        ClinicalRiskAssessment.objects.filter(transaction=dispensing_transaction).delete()


@transaction.atomic
def acknowledge_alerts(dispensing_transaction, user, note=''):
    now = timezone.now()
    dispensing_transaction.clinical_alerts.filter(status=ClinicalCheckStatus.WARNING).update(
        acknowledged_by=user,
        acknowledged_at=now,
        acknowledgement_note=note.strip(),
    )
