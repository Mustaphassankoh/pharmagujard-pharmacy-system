from decimal import Decimal, InvalidOperation

from django.conf import settings


def format_currency(value):
    """Format a monetary value without converting it through binary float."""
    if value is None or value == '':
        return ''

    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ''

    places = settings.CURRENCY_DECIMAL_PLACES
    return f"{settings.CURRENCY_CODE} {amount:,.{places}f}"
