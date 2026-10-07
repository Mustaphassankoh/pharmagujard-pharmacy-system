import csv
import json
from functools import wraps

from django.contrib.auth import get_user_model
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    TenantAllergenForm, TenantAllergyRuleForm, TenantDosageRuleForm,
    TenantDrugInteractionRuleForm,
)
from .governance import (
    activate_rule, approve_rule, create_rule, create_rule_version, retire_rule,
    submit_rule_for_review,
)
from .models import (
    Allergen, AllergyRule, ClinicalRuleAudit, DosageRule, DrugInteractionRule,
    RuleLifecycleStatus, SeverityChoices,
)
from .reporting import (
    EXPIRY_WINDOW_DAYS, RULE_TYPES, effective_state, get_action_required_rules,
    get_all_rule_rows, get_filtered_rule_rows, get_governance_summary,
    get_audit_queryset, get_recent_governance_activity, get_rule_lineage, review_state, rule_summary,
)

User = get_user_model()

TENANT_RULE_TYPES = {
    'interaction': (DrugInteractionRule, TenantDrugInteractionRuleForm, 'Drug Interaction Rule'),
    'allergy': (AllergyRule, TenantAllergyRuleForm, 'Allergy Rule'),
    'dosage': (DosageRule, TenantDosageRuleForm, 'Dosage Rule'),
}


def governance_admin_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not (request.user.is_superuser or getattr(request.user, 'role', None) == 'ADMIN'):
            raise PermissionDenied('Clinical governance reporting is restricted to administrators.')
        return view(request, *args, **kwargs)
    return wrapped


def tenant_governance_admin_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if getattr(request.user, 'role', None) != 'ADMIN' or not request.user.pharmacy_id:
            raise PermissionDenied('Clinical knowledge management is restricted to pharmacy administrators.')
        return view(request, *args, **kwargs)
    return wrapped


def _query_without_page(request):
    query = request.GET.copy()
    query.pop('page', None)
    return query.urlencode()


@require_GET
@governance_admin_required
def governance_dashboard(request):
    rows = get_all_rule_rows(request.user)
    queues = get_action_required_rules(rows)
    return render(request, 'clinical/governance_dashboard.html', {
        'summary': get_governance_summary(rows), 'queues': queues,
        'recent_activity': get_recent_governance_activity(10, request.user),
        'expiry_window_days': EXPIRY_WINDOW_DAYS,
    })


@require_GET
@tenant_governance_admin_required
def rule_management(request):
    rows = get_all_rule_rows(request.user)
    for row in rows:
        row['effective_state'] = effective_state(row['object'])
    return render(request, 'clinical/rule_management.html', {
        'rule_sections': [
            ('Drug Interaction Rules', [row for row in rows if row['rule_type'] == 'interaction']),
            ('Allergy Rules', [row for row in rows if row['rule_type'] == 'allergy']),
            ('Dosage Rules', [row for row in rows if row['rule_type'] == 'dosage']),
        ],
        'allergens': Allergen.objects.filter(pharmacy_id=request.user.pharmacy_id).order_by('name'),
        'has_rules': bool(rows),
    })


@tenant_governance_admin_required
def allergen_create(request):
    form = TenantAllergenForm(request.POST or None, pharmacy=request.user.pharmacy)
    if request.method == 'POST' and form.is_valid():
        allergen = form.save(commit=False)
        allergen.pharmacy = request.user.pharmacy
        try:
            allergen.save()
        except IntegrityError:
            form.add_error('name', 'An allergen with this name already exists for this pharmacy.')
            return render(request, 'clinical/knowledge_form.html', {
                'form': form, 'title': 'Add Allergen', 'submit_label': 'Add Allergen',
            })
        messages.success(request, 'Allergen added successfully.')
        return redirect('clinical:rule_management')
    return render(request, 'clinical/knowledge_form.html', {
        'form': form, 'title': 'Add Allergen', 'submit_label': 'Add Allergen',
    })


@tenant_governance_admin_required
def allergen_update(request, pk):
    allergen = get_object_or_404(Allergen, pk=pk, pharmacy_id=request.user.pharmacy_id)
    form = TenantAllergenForm(request.POST or None, instance=allergen, pharmacy=request.user.pharmacy)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Allergen updated successfully.')
        return redirect('clinical:rule_management')
    return render(request, 'clinical/knowledge_form.html', {
        'form': form, 'title': 'Edit Allergen', 'submit_label': 'Save Changes',
    })


@tenant_governance_admin_required
def rule_create(request, rule_type):
    if rule_type not in TENANT_RULE_TYPES:
        raise PermissionDenied('Unknown clinical rule type.')
    model, form_class, label = TENANT_RULE_TYPES[rule_type]
    form = form_class(request.POST or None, pharmacy=request.user.pharmacy)
    if request.method == 'POST' and form.is_valid():
        try:
            data = form.cleaned_data.copy()
            reason = data.pop('change_reason', '')
            create_rule(model, request.user, reason=reason, **data)
        except ValidationError as exc:
            form.add_error(None, exc)
        except IntegrityError:
            form.add_error(None, 'A matching rule version already exists for this pharmacy.')
        else:
            messages.success(request, f'{label} created as a draft.')
            return redirect('clinical:rule_management')
    return render(request, 'clinical/knowledge_form.html', {
        'form': form, 'title': f'Add {label}', 'submit_label': 'Create Draft Rule',
        'is_rule_form': True,
    })


@require_POST
@tenant_governance_admin_required
def rule_lifecycle_action(request, rule_type, pk, action):
    if rule_type not in TENANT_RULE_TYPES:
        raise PermissionDenied('Unknown clinical rule type.')
    model = TENANT_RULE_TYPES[rule_type][0]
    rule = get_object_or_404(model, pk=pk, pharmacy_id=request.user.pharmacy_id)
    reason = request.POST.get('reason', '').strip()
    actions = {
        'submit': lambda: submit_rule_for_review(rule, request.user, reason),
        'approve': lambda: approve_rule(rule, request.user, reason),
        'activate': lambda: activate_rule(rule, request.user, reason),
        'retire': lambda: retire_rule(rule, request.user, reason),
        'version': lambda: create_rule_version(rule, request.user, reason),
    }
    if action not in actions:
        raise PermissionDenied('Unknown lifecycle action.')
    try:
        actions[action]()
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    else:
        messages.success(request, 'Clinical rule lifecycle updated successfully.')
    return redirect('clinical:rule_management')


@require_GET
@governance_admin_required
def rule_report(request):
    rows = get_filtered_rule_rows(request.GET, request.user)
    page = Paginator(rows, 25).get_page(request.GET.get('page'))
    return render(request, 'clinical/rule_report.html', {
        'page_obj': page, 'query_without_page': _query_without_page(request),
        'rule_types': RULE_TYPES, 'statuses': RuleLifecycleStatus.choices,
        'severities': SeverityChoices.choices,
        'users': User.objects.filter(is_active=True, pharmacy_id=request.user.pharmacy_id).order_by('username') if not request.user.is_superuser else User.objects.filter(is_active=True).order_by('username'),
        'filters': request.GET,
    })


@require_GET
@governance_admin_required
def audit_report(request):
    audits = get_audit_queryset(request.user).order_by('-changed_at', '-pk')
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
    audit = get_object_or_404(get_audit_queryset(request.user), pk=pk)
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
    rules = model.objects.all() if request.user.is_superuser else model.objects.filter(pharmacy_id=request.user.pharmacy_id)
    rule = get_object_or_404(rules, pk=pk)
    lineage = get_rule_lineage(rule)
    audits = get_audit_queryset(request.user).filter(
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
    rows = get_filtered_rule_rows(request.GET, request.user)
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
    audits = get_audit_queryset(request.user).order_by('-changed_at', '-pk')
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
