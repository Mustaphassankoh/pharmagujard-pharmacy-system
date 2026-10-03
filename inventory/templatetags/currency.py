from django import template

from pharmacy_system.currency import format_currency

register = template.Library()


@register.filter(name='currency')
def currency(value):
    return format_currency(value)
