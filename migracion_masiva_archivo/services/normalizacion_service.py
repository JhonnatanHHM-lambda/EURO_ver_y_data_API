import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

MAX_DECIMAL_18_2 = Decimal('9999999999999999.99')


def normalize_text(value):
    if value is None:
        return ''
    text = str(value).upper().strip()
    text = ''.join(
        char for char in unicodedata.normalize('NFD', text)
        if unicodedata.category(char) != 'Mn'
    )
    return re.sub(r'\s+', ' ', text)


def normalize_nit(value):
    text = normalize_text(value)
    digits = re.sub(r'\D', '', text)
    if len(digits) < 2:
        return ''
    return f'{digits[:-1]}-{digits[-1]}'


def normalize_consecutivo(value):
    text = normalize_text(value)
    tokens = re.findall(r'[A-Z]+|\d+', text)
    if len(tokens) < 3:
        compact = re.sub(r'[^A-Z0-9]', '', text)
        match = re.match(r'([A-Z]{3})([A-Z]{3})(\d+)$', compact)
        if not match:
            return ''
        prefix, code, number = match.groups()
    else:
        prefix, code, number = tokens[0], tokens[1], tokens[-1]

    if not number.isdigit():
        return ''

    return f'{prefix[:3]}-{code[:3]}-{number.zfill(8)}'


def normalize_money(value):
    text = normalize_text(value)
    text = re.sub(r'[^0-9,.-]', '', text).strip('.,-')
    if not text:
        return None

    if ',' in text and '.' in text:
        if text.rfind(',') > text.rfind('.'):
            text = text.replace('.', '').replace(',', '.')
        else:
            text = text.replace(',', '')
    elif ',' in text:
        parts = text.split(',')
        if len(parts[-1]) == 2:
            text = ''.join(parts[:-1]) + '.' + parts[-1]
        else:
            text = text.replace(',', '')
    elif text.count('.') > 1:
        parts = text.split('.')
        if len(parts[-1]) == 2:
            text = ''.join(parts[:-1]) + '.' + parts[-1]
        else:
            text = ''.join(parts)

    try:
        value = Decimal(text)
    except InvalidOperation:
        return None

    if abs(value) > MAX_DECIMAL_18_2:
        return None

    return value


def normalize_date(value):
    text = normalize_text(value)
    match = re.search(r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b', text)
    if not match:
        return None

    day, month, year = match.groups()
    year = int(year)
    if year < 100:
        year += 2000

    try:
        return date(year, int(month), int(day))
    except ValueError:
        return None


def normalize_reference(value):
    text = normalize_text(value)
    return re.sub(r'[^A-Z0-9-]', '', text)


