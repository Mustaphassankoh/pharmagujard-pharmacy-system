import csv
import json
from functools import wraps

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .models import ClinicalRuleAudit, RuleLifecycleStatus, SeverityChoices
from .reporting import (
    EXPIRY_WINDOW_DAYS, RULE_TYPES, effective_state, get_action_required_rules,
    get_all_rule_rows, get_filtered_rule_rows, get_governance_summary,
    get_recent_governance_activity, get_rule_lineage, review_state, rule_summary,
)

User = get_user_model()


def governance_admin_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not (request.user.is_superuser or getattr(request.user, 'role', None) == 'ADMIN'):
            raise PermissionDenied('Clinical governance reporting is restricted to administrators.')
        return view(request, *args, **kwargs)
    return wrapped


def _query_without_page(request):
    query = request.GET.copy()
    query.pop('page', None)
    return query.urlencode()


@require_GET
@governance_admin_required
def governance_dashboard(request):
    rows = get_all_rule_rows()
    queues = get_action_required_rules(rows)
    return render(request, 'clinical/governance_dashboard.html', {
        'summary': get_governance_summary(rows), 'queues': queues,
        'recent_activity': get_recent_governance_activity(10),
        'expiry_window_days': EXPIRY_WINDOW_DAYS,
    })


@require_GET
@governance_admin_required
def rule_report(request):
    rows = get_filtered_rule_rows(request.GET)
    page = Paginator(rows, 25).get_page(request.GET.get('page'))
    return render(request, 'clinical/rule_report.html', {
        'page_obj': page, 'query_without_page': _query_without_page(request),
        'rule_types': RULE_TYPES, 'statuses': RuleLifecycleStatus.choices,
        'severities': SeverityChoices.choices,
        'users': User.objects.filter(is_active=True).order_by('username'),
        'filters': request.GET,
    })


@require_GET
@governance_admin_required
def audit_report(request):
    audits = ClinicalRuleAudit.objects.select_related('changed_by').order_by('-changed_at', '-pk')
    if request.GET.get('rule_type'):
        audits = audits.filter(rule_type=request.GET['rule_type'])
    if request.GET.get('action'):
        audits = audits.filter(action=request.GET['action'])
    page = Paginator(audits, 25).get_page(request.GET.get('page'))
    return render(request, 'clinical/audit_report.html', {
        'page_obj': page, 'query_without_page': _query_without_page(request),
        'rule_types': RULE_TYPES, 'actions': ClinicalRuleAudit._meta.get_field('action').choices,
        'filters': request.GET,
    })


@require_GET
@governance_admin_required
def audit_detail(request, pk):
    audit = get_object_or_404(ClinicalRuleAudit.objects.select_related('changed_by'), pk=pk)
    return render(request, 'clinical/audit_detail.html', {
        'audit': audit,
        'before_json': json.dumps(audit.before_snapshot, indent=2, sort_keys=True),
        'after_json': json.dumps(audit.after_snapshot, indent=2, sort_keys=True),
    })


@require_GET
@governance_admin_required
def rule_history(request, rule_type, pk):
    if rule_type not in RULE_TYPES:
        raise PermissionDenied('Unknown governed rule type.')
    model = RULE_TYPES[rule_type][0]
    rule = get_object_or_404(model, pk=pk)
    lineage = get_rule_lineage(rule)
    audits = ClinicalRuleAudit.objects.filter(
        rule_type=model.__name__, rule_object_id__in=[item.pk for item in lineage],
    ).select_related('changed_by').order_by('-changed_at', '-pk')
    page = Paginator(audits, 25).get_page(request.GET.get('page'))
    return render(request, 'clinical/rule_history.html', {
        'rule': rule, 'row': rule_summary(rule, rule_type), 'lineage': lineage,
        'page_obj': page, 'rule_type': rule_type,
    })


@require_GET
@governance_admin_required
def export_rules_csv(request):
    rows = get_filtered_rule_rows(request.GET)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="clinical-governance-rules.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'rule_type', 'object_id', 'version', 'status', 'effective_state', 'severity',
        'medicine', 'allergen', 'effective_from', 'effective_to', 'next_review_date',
        'review_state', 'source_reference', 'source_title', 'source_version',
        'created_by', 'approved_by', 'created_at', 'updated_at',
    ])
    for row in rows:
        rule = row['object']
        writer.writerow([
            row['rule_type_label'], rule.pk, rule.version, rule.status, effective_state(rule), rule.severity,
            row['medicine'], row['allergen'], rule.effective_from or '', rule.effective_to or '',
            rule.next_review_date or '', review_state(rule), rule.source_reference, rule.source_title,
            rule.source_version, rule.created_by.username if rule.created_by else '',
            rule.approved_by.username if rule.approved_by else '', rule.created_at, rule.updated_at,
        ])
    return response


@require_GET
@governance_admin_required
def export_audits_csv(request):
    audits = ClinicalRuleAudit.objects.select_related('changed_by').order_by('-changed_at', '-pk')
    if request.GET.get('rule_type'):
        audits = audits.filter(rule_type=request.GET['rule_type'])
    if request.GET.get('action'):
        audits = audits.filter(action=request.GET['action'])
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="clinical-governance-audit.csv"'
    writer = csv.writer(response)
    writer.writerow(['audit_id', 'rule_type', 'object_id', 'version', 'action', 'changed_by', 'changed_at', 'reason'])
    for audit in audits:
        writer.writerow([
            audit.pk, audit.rule_type, audit.rule_object_id, audit.rule_version, audit.action,
            audit.changed_by.username if audit.changed_by else '', audit.changed_at, audit.change_reason,
        ])
    return response
