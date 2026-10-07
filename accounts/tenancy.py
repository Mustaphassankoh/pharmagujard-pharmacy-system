from django.shortcuts import get_object_or_404


def scope_queryset(queryset, user, lookup='pharmacy'):
    """Restrict a queryset to the signed-in user's pharmacy when one is assigned."""
    if user.is_superuser:
        return queryset
    pharmacy_id = getattr(user, 'pharmacy_id', None)
    return queryset.filter(**{f'{lookup}_id': pharmacy_id})


def scope_to_pharmacy(queryset, pharmacy, lookup='pharmacy'):
    return queryset.filter(**{f'{lookup}_id': getattr(pharmacy, 'pk', None)})


def get_tenant_object_or_404(queryset, user, lookup='pharmacy', **kwargs):
    return get_object_or_404(scope_queryset(queryset, user, lookup), **kwargs)
