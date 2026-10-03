"""Shared lifecycle, versioning, eligibility, and audit services for clinical rules."""
from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.forms.models import model_to_dict
from django.utils import timezone

from .models import ClinicalRuleAudit, RuleAuditAction, RuleLifecycleStatus


RULE_MODELS = ('DrugInteractionRule', 'AllergyRule', 'DosageRule')


def require_governance_admin(user):
    if not user or not user.is_authenticated or not (user.is_superuser or getattr(user, 'role', None) == 'ADMIN'):
        raise PermissionDenied('Only an administrator may manage clinical-rule governance.')


def effective_rules(queryset, at_time=None):
    at_time = at_time or timezone.now()
    return queryset.filter(
        is_active=True, status=RuleLifecycleStatus.ACTIVE, retired_at__isnull=True,
    ).filter(
        Q(effective_from__isnull=True) | Q(effective_from__lte=at_time),
        Q(effective_to__isnull=True) | Q(effective_to__gte=at_time),
    )


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, 'pk'):
        return value.pk
    return value


def rule_snapshot(rule):
    data = model_to_dict(rule)
    data['id'] = rule.pk
    return {key: _json_value(value) for key, value in data.items()}


def record_rule_audit(rule, action, user, reason='', before=None):
    return ClinicalRuleAudit.objects.create(
        rule_type=rule.__class__.__name__, rule_object_id=rule.pk, rule_version=rule.version,
        action=action, changed_by=user, change_reason=(reason or '').strip(),
        before_snapshot=before or {}, after_snapshot=rule_snapshot(rule),
    )


def _locked(rule):
    if rule.__class__.__name__ not in RULE_MODELS:
        raise ValidationError('Unsupported clinical rule type.')
    return rule.__class__.objects.select_for_update().get(pk=rule.pk)


@transaction.atomic
def create_rule(rule_model, user, reason='', **fields):
    require_governance_admin(user)
    if rule_model.__name__ not in RULE_MODELS:
        raise ValidationError('Unsupported clinical rule type.')
    rule = rule_model(created_by=user, change_reason=(reason or '').strip(), **fields)
    rule.save()
    record_rule_audit(rule, RuleAuditAction.CREATED, user, reason)
    return rule


@transaction.atomic
def submit_rule_for_review(rule, user, reason=''):
    require_governance_admin(user)
    rule = _locked(rule)
    if rule.status != RuleLifecycleStatus.DRAFT:
        raise ValidationError('Only a draft rule can be submitted for review.')
    before = rule_snapshot(rule)
    rule.status = RuleLifecycleStatus.UNDER_REVIEW
    rule.change_reason = reason.strip()
    rule.save()
    record_rule_audit(rule, RuleAuditAction.SUBMITTED_FOR_REVIEW, user, reason, before)
    return rule


@transaction.atomic
def approve_rule(rule, user, reason=''):
    require_governance_admin(user)
    rule = _locked(rule)
    if rule.status != RuleLifecycleStatus.UNDER_REVIEW:
        raise ValidationError('Only a rule under review can be approved.')
    if rule.created_by_id and rule.created_by_id == user.pk and not user.is_superuser:
        raise ValidationError('The rule creator cannot approve their own rule.')
    before = rule_snapshot(rule)
    now = timezone.now()
    rule.reviewed_by = user
    rule.reviewed_at = now
    rule.approved_by = user
    rule.approved_at = now
    rule.status = RuleLifecycleStatus.APPROVED
    rule.change_reason = reason.strip()
    rule.save()
    record_rule_audit(rule, RuleAuditAction.REVIEWED, user, reason, before)
    record_rule_audit(rule, RuleAuditAction.APPROVED, user, reason, before)
    return rule


@transaction.atomic
def activate_rule(rule, user, reason=''):
    require_governance_admin(user)
    rule = _locked(rule)
    if rule.status != RuleLifecycleStatus.APPROVED:
        raise ValidationError('Only an approved rule can be activated.')
    if not rule.source_reference.strip():
        raise ValidationError('A verified source reference is required before activation.')
    before = rule_snapshot(rule)
    rule.status = RuleLifecycleStatus.ACTIVE
    rule.is_active = True
    rule.change_reason = reason.strip()
    rule.full_clean()
    rule.save()
    record_rule_audit(rule, RuleAuditAction.ACTIVATED, user, reason, before)
    if rule.supersedes_id:
        predecessor = rule.__class__.objects.select_for_update().get(pk=rule.supersedes_id)
        if predecessor.status == RuleLifecycleStatus.ACTIVE:
            predecessor_before = rule_snapshot(predecessor)
            predecessor.status = RuleLifecycleStatus.RETIRED
            predecessor.is_active = False
            predecessor.retired_by = user
            predecessor.retired_at = timezone.now()
            predecessor.change_reason = f'Superseded by version {rule.version}. {reason}'.strip()
            predecessor.save()
            record_rule_audit(predecessor, RuleAuditAction.SUPERSEDED, user, reason, predecessor_before)
    return rule


@transaction.atomic
def retire_rule(rule, user, reason):
    require_governance_admin(user)
    if not (reason or '').strip():
        raise ValidationError('A retirement reason is required.')
    rule = _locked(rule)
    if rule.status != RuleLifecycleStatus.ACTIVE:
        raise ValidationError('Only an active rule can be retired.')
    before = rule_snapshot(rule)
    rule.status = RuleLifecycleStatus.RETIRED
    rule.is_active = False
    rule.retired_by = user
    rule.retired_at = timezone.now()
    rule.change_reason = reason.strip()
    rule.save()
    record_rule_audit(rule, RuleAuditAction.RETIRED, user, reason, before)
    return rule


@transaction.atomic
def create_rule_version(rule, user, reason, changes=None):
    require_governance_admin(user)
    if not (reason or '').strip():
        raise ValidationError('A change reason is required for a new version.')
    rule = _locked(rule)
    changes = changes or {}
    disallowed = {'id', 'pk', 'version', 'status', 'supersedes', 'created_by', 'approved_by', 'retired_by'}
    if disallowed.intersection(changes):
        raise ValidationError('Version identity and lifecycle fields cannot be supplied as clinical changes.')
    field_names = [
        field.name for field in rule._meta.concrete_fields
        if not field.primary_key and field.name not in {
            'version', 'status', 'created_by', 'reviewed_by', 'reviewed_at', 'approved_by', 'approved_at',
            'retired_by', 'retired_at', 'change_reason', 'supersedes', 'created_at', 'updated_at',
        }
    ]
    values = {}
    for name in field_names:
        field = rule._meta.get_field(name)
        values[field.attname if field.is_relation else name] = getattr(rule, field.attname if field.is_relation else name)
    values.update(changes)
    values.update({
        'version': rule.version + 1, 'status': RuleLifecycleStatus.DRAFT,
        'created_by': user, 'change_reason': reason.strip(), 'supersedes': rule,
        'is_active': True,
    })
    new_rule = rule.__class__(**values)
    new_rule.save()
    record_rule_audit(new_rule, RuleAuditAction.CREATED, user, reason)
    return new_rule
