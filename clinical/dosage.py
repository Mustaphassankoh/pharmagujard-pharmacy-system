"""Deterministic structured dosage checking; no free-text parsing."""
import hashlib
import json
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from dispensing.models import TransactionStatusChoices, TransactionTypeChoices

from .models import (
    AlertTypeChoices, ClinicalAlert, ClinicalCheckResult, ClinicalCheckStatus,
    ClinicalCheckType, DosageAlertReason, DosageRule,
)
from .governance import effective_rules


def _decimal(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _structured_items(dispensing_transaction, dosage_input=None):
    if isinstance(dosage_input, dict):
        return [dict(line, medicine_id=int(key)) for key, line in dosage_input.items()]
    items = {}
    for item in dispensing_transaction.items.all().order_by('medicine_id', 'pk'):
        items.setdefault(item.medicine_id, {
            'medicine_id': item.medicine_id,
            'medicine_name': str(item.medicine),
            'dose_amount': item.dose_amount,
            'dose_unit': item.dose_unit,
            'frequency_per_day': item.frequency_per_day,
            'duration_days': item.duration_days,
        })
    if dosage_input is not None and not isinstance(dosage_input, dict):
        existing = set(items)
        for medicine_id in dosage_input:
            medicine_id = int(medicine_id)
            if medicine_id not in existing:
                items[medicine_id] = {'medicine_id': medicine_id}
    return list(items.values())


def dosage_fingerprint(dispensing_transaction, dosage_input=None):
    consultation = getattr(dispensing_transaction, 'consultation', None)
    payload = {
        'items': sorted(({
            'medicine_id': int(item['medicine_id']),
            'dose_amount': str(item.get('dose_amount') or ''),
            'dose_unit': item.get('dose_unit') or '',
            'frequency_per_day': str(item.get('frequency_per_day') or ''),
            'duration_days': str(item.get('duration_days') or ''),
        } for item in _structured_items(dispensing_transaction, dosage_input)), key=lambda row: row['medicine_id']),
        'age': consultation.age if consultation else None,
        'weight': str(consultation.weight) if consultation and consultation.weight is not None else None,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _snapshot(item, rule, daily_dose, reason, limit):
    return {
        'medicine_id': int(item['medicine_id']),
        'medicine_name': item.get('medicine_name') or rule.medicine.generic_name,
        'entered_dose': str(item.get('dose_amount') or ''),
        'dose_unit': item.get('dose_unit') or '',
        'frequency_per_day': str(item.get('frequency_per_day') or ''),
        'duration_days': item.get('duration_days'),
        'calculated_daily_dose': str(daily_dose) if daily_dose is not None else None,
        'applicable_limit': str(limit),
        'reason': reason,
        'rule_description': rule.description,
        'explanation': rule.explanation,
        'recommendation': rule.recommendation,
        'source_reference': rule.source_reference,
        'rule_version': rule.version,
    }


@transaction.atomic
def check_dosage(dispensing_transaction, dosage_input=None):
    """Evaluate each medicine's explicit structured dosage against every applicable rule."""
    result, _ = ClinicalCheckResult.objects.select_for_update().get_or_create(
        transaction=dispensing_transaction, check_type=ClinicalCheckType.DOSAGE,
    )
    if dispensing_transaction.status != TransactionStatusChoices.DRAFT:
        alerts = list(dispensing_transaction.clinical_alerts.filter(alert_type=AlertTypeChoices.DOSAGE))
        return {'status': result.status, 'alerts': alerts, 'details': result.details}

    ClinicalAlert.objects.filter(transaction=dispensing_transaction, alert_type=AlertTypeChoices.DOSAGE).delete()
    items = _structured_items(dispensing_transaction, dosage_input)
    consultation = getattr(dispensing_transaction, 'consultation', None)
    age = consultation.age if consultation else None
    weight = consultation.weight if consultation else None
    alerts, item_details = [], []
    evaluated_count = 0
    unresolved = []

    for item in items:
        medicine_id = int(item['medicine_id'])
        amount = _decimal(item.get('dose_amount'))
        unit = item.get('dose_unit') or ''
        frequency = _decimal(item.get('frequency_per_day'))
        duration = item.get('duration_days')
        detail = {'medicine_id': medicine_id, 'status': ClinicalCheckStatus.NOT_CHECKED}
        if amount is None or not unit:
            detail['reason'] = 'No structured dosage information was available for automated dosage checking.'
            unresolved.append(detail['reason'])
            item_details.append(detail)
            continue
        all_rules = list(effective_rules(DosageRule.objects.filter(medicine_id=medicine_id)).select_related('medicine'))
        if not all_rules:
            detail['reason'] = 'No verified dosage rule is configured for this medicine.'
            unresolved.append(detail['reason'])
            item_details.append(detail)
            continue
        rules = [rule for rule in all_rules if rule.dose_unit == unit]
        if not rules:
            detail['reason'] = 'The structured dose unit is incompatible with the configured dosage rules.'
            unresolved.append(detail['reason'])
            item_details.append(detail)
            continue

        applicable = []
        missing_context = []
        for rule in rules:
            if (rule.min_age is not None or rule.max_age is not None) and age is None:
                missing_context.append('Age required by an applicable dosage rule was not provided.')
                continue
            if (rule.min_weight is not None or rule.max_weight is not None) and weight is None:
                missing_context.append('Weight required by an applicable dosage rule was not provided.')
                continue
            if rule.min_age is not None and age < rule.min_age or rule.max_age is not None and age > rule.max_age:
                continue
            if rule.min_weight is not None and weight < rule.min_weight or rule.max_weight is not None and weight > rule.max_weight:
                continue
            applicable.append(rule)
        if not applicable:
            detail['reason'] = missing_context[0] if missing_context else 'No verified dosage rule applies to the available age and weight context.'
            unresolved.append(detail['reason'])
            item_details.append(detail)
            continue

        evaluated_count += 1
        daily_dose = amount * frequency if frequency is not None else None
        violations = []
        incomplete = []
        if frequency is None and any(
            rule.max_daily_dose is not None or rule.min_frequency_per_day is not None or rule.max_frequency_per_day is not None
            for rule in applicable
        ):
            incomplete.append('Frequency per day is required by the applicable dosage rule but was not provided.')
        if duration is None and any(rule.max_duration_days is not None for rule in applicable):
            incomplete.append('Duration in days is required by the applicable dosage rule but was not provided.')
        for rule in applicable:
            checks = (
                (rule.min_single_dose is not None and amount < rule.min_single_dose, DosageAlertReason.BELOW_SINGLE_DOSE, rule.min_single_dose, 'The entered single dose is below the configured minimum.'),
                (rule.max_single_dose is not None and amount > rule.max_single_dose, DosageAlertReason.ABOVE_SINGLE_DOSE, rule.max_single_dose, 'The entered single dose exceeds the configured maximum.'),
                (rule.max_daily_dose is not None and daily_dose is not None and daily_dose > rule.max_daily_dose, DosageAlertReason.ABOVE_DAILY_DOSE, rule.max_daily_dose, 'The calculated daily dose exceeds the configured maximum.'),
                (rule.min_frequency_per_day is not None and frequency is not None and frequency < rule.min_frequency_per_day, DosageAlertReason.FREQUENCY_TOO_LOW, rule.min_frequency_per_day, 'The entered frequency is below the configured minimum.'),
                (rule.max_frequency_per_day is not None and frequency is not None and frequency > rule.max_frequency_per_day, DosageAlertReason.FREQUENCY_TOO_HIGH, rule.max_frequency_per_day, 'The entered frequency exceeds the configured maximum.'),
                (rule.max_duration_days is not None and duration is not None and duration > rule.max_duration_days, DosageAlertReason.DURATION_TOO_LONG, rule.max_duration_days, 'The entered duration exceeds the configured maximum.'),
            )
            for violated, reason, limit, trigger in checks:
                if not violated:
                    continue
                snapshot = _snapshot(item, rule, daily_dose, reason, limit)
                alert = ClinicalAlert.objects.create(
                    transaction=dispensing_transaction, alert_type=AlertTypeChoices.DOSAGE,
                    severity=rule.severity, status=ClinicalCheckStatus.WARNING,
                    medicine_a=rule.medicine, title=f'Dosage warning: {rule.medicine.generic_name}',
                    description=rule.description, explanation=f'{trigger} {rule.explanation}',
                    recommendation=rule.recommendation, source_reference=rule.source_reference,
                    dosage_rule_reference=rule, dosage_reason=reason, snapshot_details=snapshot,
                )
                alerts.append(alert)
                violations.append(reason)
        detail.update({
            'status': ClinicalCheckStatus.WARNING if violations else (ClinicalCheckStatus.NOT_CHECKED if incomplete else ClinicalCheckStatus.PASSED),
            'calculated_daily_dose': str(daily_dose) if daily_dose is not None else None,
            'dose_unit': unit, 'violations': violations,
        })
        if incomplete:
            detail['reason'] = incomplete[0]
            unresolved.extend(incomplete)
        item_details.append(detail)

    if alerts:
        status = ClinicalCheckStatus.WARNING
    elif unresolved:
        status = ClinicalCheckStatus.NOT_CHECKED
    elif evaluated_count:
        status = ClinicalCheckStatus.PASSED
    else:
        status = ClinicalCheckStatus.NOT_CHECKED
        unresolved.append('No structured dosage information was available for automated dosage checking.')
    details = {
        'execution_failed': False,
        'context_unavailable': status == ClinicalCheckStatus.NOT_CHECKED,
        'reason': unresolved[0] if unresolved else '',
        'evaluated_item_count': evaluated_count,
        'items': item_details,
    }
    result.status = status
    result.input_fingerprint = dosage_fingerprint(dispensing_transaction, dosage_input)
    result.checked_at = timezone.now()
    result.details = details
    result.save()
    return {'status': status, 'alerts': alerts, 'details': details}
