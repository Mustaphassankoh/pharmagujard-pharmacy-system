"""Read-only reporting helpers for governed clinical knowledge."""
from collections import Counter
from datetime import date, datetime, timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import AllergyRule, ClinicalRuleAudit, DosageRule, DrugInteractionRule, RuleLifecycleStatus

EXPIRY_WINDOW_DAYS = 30
RULE_TYPES = {
    'interaction': (DrugInteractionRule, 'Drug Interaction'),
    'allergy': (AllergyRule, 'Allergy'),
    'dosage': (DosageRule, 'Dosage'),
}


def _rule_queryset(key):
    model = RULE_TYPES[key][0]
    related = ['created_by', 'reviewed_by', 'approved_by', 'retired_by', 'supersedes']
    if key == 'interaction':
        related += ['medicine_a', 'medicine_b']
    elif key == 'allergy':
        related += ['medicine', 'allergen']
    else:
        related += ['medicine']
    return model.objects.select_related(*related)


def rule_summary(rule, key):
    if key == 'interaction':
        summary = f'{rule.medicine_a.generic_name} + {rule.medicine_b.generic_name}'
        medicine = summary
        allergen = ''
    elif key == 'allergy':
        summary = f'{rule.allergen.name} + {rule.medicine.generic_name}'
        medicine, allergen = rule.medicine.generic_name, rule.allergen.name
    else:
        summary = f'{rule.medicine.generic_name} ({rule.dose_unit})'
        medicine, allergen = rule.medicine.generic_name, ''
    return {
        'object': rule, 'rule_type': key, 'rule_type_label': RULE_TYPES[key][1],
        'summary': summary, 'medicine': medicine, 'allergen': allergen,
    }


def get_all_rule_rows():
    rows = []
    for key in RULE_TYPES:
        rows.extend(rule_summary(rule, key) for rule in _rule_queryset(key))
    return rows


def effective_state(rule, now=None):
    now = now or timezone.now()
    if rule.status == RuleLifecycleStatus.RETIRED or rule.retired_at or not rule.is_active:
        return 'retired'
    if rule.status != RuleLifecycleStatus.ACTIVE:
        return 'inactive'
    if rule.effective_from and rule.effective_from > now:
        return 'future'
    if rule.effective_to and rule.effective_to < now:
        return 'expired'
    return 'effective'


def review_state(rule, today=None, days=EXPIRY_WINDOW_DAYS):
    today = today or timezone.localdate()
    if not rule.next_review_date:
        return 'none'
    if rule.next_review_date < today:
        return 'overdue'
    if rule.next_review_date <= today + timedelta(days=days):
        return 'due_soon'
    return 'scheduled'


def is_expiring_soon(rule, now=None, days=EXPIRY_WINDOW_DAYS):
    now = now or timezone.now()
    return (
        effective_state(rule, now) == 'effective' and rule.effective_to is not None
        and now <= rule.effective_to <= now + timedelta(days=days)
    )


def get_governance_summary(rows=None, now=None):
    rows = rows if rows is not None else get_all_rule_rows()
    now = now or timezone.now()
    statuses = Counter(row['object'].status for row in rows)
    states = Counter(effective_state(row['object'], now) for row in rows)
    reviews = Counter(review_state(row['object']) for row in rows)
    by_type = {}
    for key, (_, label) in RULE_TYPES.items():
        typed = [row for row in rows if row['rule_type'] == key]
        by_type[key] = {
            'label': label, 'total': len(typed),
            'active': sum(row['object'].status == RuleLifecycleStatus.ACTIVE for row in typed),
            'draft': sum(row['object'].status == RuleLifecycleStatus.DRAFT for row in typed),
            'retired': sum(row['object'].status == RuleLifecycleStatus.RETIRED for row in typed),
            'expiring_soon': sum(is_expiring_soon(row['object'], now) for row in typed),
        }
    return {
        'total': len(rows), 'draft': statuses[RuleLifecycleStatus.DRAFT],
        'under_review': statuses[RuleLifecycleStatus.UNDER_REVIEW],
        'approved': statuses[RuleLifecycleStatus.APPROVED],
        'active': statuses[RuleLifecycleStatus.ACTIVE], 'retired': statuses[RuleLifecycleStatus.RETIRED],
        'currently_effective': states['effective'], 'future': states['future'], 'expired': states['expired'],
        'expiring_soon': sum(is_expiring_soon(row['object'], now) for row in rows),
        'review_overdue': reviews['overdue'], 'review_due_soon': reviews['due_soon'],
        'no_review_date': reviews['none'], 'by_type': by_type,
    }


def get_action_required_rules(rows=None, now=None, days=EXPIRY_WINDOW_DAYS):
    rows = rows if rows is not None else get_all_rule_rows()
    now = now or timezone.now()
    return {
        'draft': [row for row in rows if row['object'].status == RuleLifecycleStatus.DRAFT],
        'under_review': [row for row in rows if row['object'].status == RuleLifecycleStatus.UNDER_REVIEW],
        'approved': [row for row in rows if row['object'].status == RuleLifecycleStatus.APPROVED],
        'review_due': [row for row in rows if review_state(row['object'], days=days) in ('overdue', 'due_soon')],
        'expiring_soon': [row for row in rows if is_expiring_soon(row['object'], now, days)],
    }


def get_recent_governance_activity(limit=10):
    return ClinicalRuleAudit.objects.select_related('changed_by').order_by('-changed_at', '-pk')[:limit]


def get_filtered_rule_rows(params):
    selected_type = params.get('rule_type', '')
    keys = [selected_type] if selected_type in RULE_TYPES else list(RULE_TYPES)
    rows = []
    for key in keys:
        qs = _rule_queryset(key)
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        if params.get('severity'):
            qs = qs.filter(severity=params['severity'])
        if params.get('version', '').isdigit():
            qs = qs.filter(version=int(params['version']))
        if params.get('creator', '').isdigit():
            qs = qs.filter(created_by_id=int(params['creator']))
        if params.get('approver', '').isdigit():
            qs = qs.filter(approved_by_id=int(params['approver']))
        start, end = parse_date(params.get('date_from', '')), parse_date(params.get('date_to', ''))
        if start:
            qs = qs.filter(Q(effective_to__isnull=True) | Q(effective_to__date__gte=start))
        if end:
            qs = qs.filter(Q(effective_from__isnull=True) | Q(effective_from__date__lte=end))
        search = params.get('q', '').strip()
        if search:
            common = Q(description__icontains=search) | Q(source_reference__icontains=search) | Q(source_title__icontains=search)
            if key == 'interaction':
                common |= Q(medicine_a__generic_name__icontains=search) | Q(medicine_b__generic_name__icontains=search)
            elif key == 'allergy':
                common |= Q(medicine__generic_name__icontains=search) | Q(allergen__name__icontains=search)
            else:
                common |= Q(medicine__generic_name__icontains=search)
            qs = qs.filter(common)
        rows.extend(rule_summary(rule, key) for rule in qs)

    state = params.get('effective_state', '')
    review = params.get('review_state', '')
    if state:
        rows = [row for row in rows if effective_state(row['object']) == state]
    if review:
        rows = [row for row in rows if review_state(row['object']) == review]
    sorting = params.get('sort', '-updated')
    reverse = sorting.startswith('-')
    field = sorting.lstrip('-')
    getters = {
        'updated': lambda row: row['object'].updated_at,
        'created': lambda row: row['object'].created_at,
        'version': lambda row: row['object'].version,
        'status': lambda row: row['object'].status,
        'effective': lambda row: row['object'].effective_from or timezone.make_aware(datetime.min),
        'review': lambda row: row['object'].next_review_date or date.min,
    }
    rows.sort(key=getters.get(field, getters['updated']), reverse=reverse)
    return rows


def get_rule_lineage(rule):
    model = rule.__class__
    all_rules = list(model.objects.select_related('created_by', 'reviewed_by', 'approved_by', 'retired_by', 'supersedes'))
    by_id = {item.pk: item for item in all_rules}
    root = rule
    seen = set()
    while root.supersedes_id and root.pk not in seen:
        seen.add(root.pk)
        root = by_id.get(root.supersedes_id, root.supersedes)
    lineage, frontier = [], [root]
    while frontier:
        item = frontier.pop(0)
        if item.pk in {existing.pk for existing in lineage}:
            continue
        lineage.append(item)
        frontier.extend(candidate for candidate in all_rules if candidate.supersedes_id == item.pk)
    return sorted(lineage, key=lambda item: (item.version, item.pk))
