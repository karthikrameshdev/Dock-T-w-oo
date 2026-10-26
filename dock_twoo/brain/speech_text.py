"""Local display-text to spoken-text normalization, shared by every TTS path.

Formatting is silent; sentence punctuation remains as prosody. Symbols carrying
meaning (currency, percentages and arithmetic) become words rather than labels.
The original document, model response and activity history are never changed.
"""
import html
import re
import unicodedata
from decimal import Decimal, localcontext

_SMALL = ('zero one two three four five six seven eight nine ten eleven twelve '
          'thirteen fourteen fifteen sixteen seventeen eighteen nineteen').split()
_TENS = 'zero ten twenty thirty forty fifty sixty seventy eighty ninety'.split()
_SCALES = ('', 'thousand', 'million', 'billion', 'trillion', 'quadrillion')
_CURRENCIES = {'$': ('dollar', 'dollars', 'cent', 'cents'),
               '€': ('euro', 'euros', 'cent', 'cents'),
               '£': ('pound', 'pounds', 'penny', 'pence'),
               '₹': ('rupee', 'rupees', 'paisa', 'paise'),
               '¥': ('yen', 'yen', None, None)}
_AMOUNT = re.compile(
    r'(?<!\w)(?P<sign>[+-]?)(?P<symbol>[$€£₹¥])\s*(?P<inner>[+-]?)\s*'
    r'(?P<number>(?:\d+(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3}|\d+)(?:\.\d+)?|\.\d+)'
    r'(?P<scale>\s*(?:thousand|million|billion|trillion)\b|[kKmMbB]\b)?', re.I)


def _integer(number):
    if number < 20:
        return _SMALL[number]
    if number < 100:
        return _TENS[number // 10] + (' ' + _SMALL[number % 10] if number % 10 else '')
    if number < 1000:
        return _SMALL[number // 100] + ' hundred' + (' ' + _integer(number % 100) if number % 100 else '')
    parts = []
    for scale in _SCALES:
        group, number = number % 1000, number // 1000
        if group:
            parts.append((_integer(group) + ' ' + scale).strip())
        if not number:
            return ' '.join(reversed(parts))
    # Arbitrarily long numbers must not overflow recursion or lose digits.
    return _integer(number) + ' quintillion ' + ' '.join(reversed(parts))


def _currency(match):
    number = match['number'].replace(',', '')
    if len(number) > 30:
        return number + ' ' + _CURRENCIES[match['symbol']][1]
    multiplier = {'k': 3, 'thousand': 3, 'm': 6, 'million': 6,
                  'b': 9, 'billion': 9, 'trillion': 12}.get((match['scale'] or '').strip().lower(), 0)
    if multiplier:
        with localcontext() as context:
            context.prec = len(number) + multiplier + 5
            number = format(Decimal(number) * (10 ** multiplier), 'f')
    whole, _, fraction = number.partition('.')
    major, majors, minor, minors = _CURRENCIES[match['symbol']]
    amount = int(whole or '0')
    if fraction and (len(fraction) > 2 or minor is None) and int(fraction):
        spoken = _integer(amount) + ' point ' + ' '.join(_SMALL[int(d)] for d in fraction) + ' ' + majors
    else:
        cents = int(fraction.ljust(2, '0')) if fraction else 0
        parts = []
        if amount or not cents:
            parts.append(_integer(amount) + ' ' + (major if amount == 1 else majors))
        if cents:
            parts.append(_integer(cents) + ' ' + (minor if cents == 1 else minors))
        spoken = ' and '.join(parts)
    return ('minus ' if '-' in (match['sign'] + match['inner']) else '') + spoken


def spoken_text(text: str) -> str:
    """Normalize whole text before phrase chunking; safe to apply repeatedly."""
    if not isinstance(text, str):
        raise TypeError('Speech text must be a string.')
    text = html.unescape(text).replace('\r\n', '\n').replace('\r', '\n')
    # Keep content/code, discard presentation syntax and fence language labels.
    text = re.sub(r'^\s*(`{3,}|~{3,})[^\n]*$', '', text, flags=re.M)
    text = re.sub(r'!?\[([^\]]*)\]\([^\n)]*\)', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\[[^\]]*\]', r'\1', text)
    text = re.sub(r'^\s*\[[^\]]+\]:\s*\S+.*$', '', text, flags=re.M)
    text = re.sub(r'</?(?:p|br|div|span|b|i|em|strong|h[1-6]|li|ul|ol|a|code|pre)\b[^>]*>', ' ', text, flags=re.I)
    text = re.sub(r'^\s*(?:[-*_]\s*){3,}$', '', text, flags=re.M)
    text = re.sub(r'^\s*(?:#{1,6}\s+|>\s*|[-+*•●]\s+)', '', text, flags=re.M)
    text = re.sub(r'\[[ xX]\]\s*', '', text)
    text = _AMOUNT.sub(_currency, text)
    text = re.sub(r'(?<=\d)\s*%', ' percent', text)
    text = re.sub(r'\bC\+\+', 'C plus plus', text)
    text = re.sub(r'\bC#', 'C sharp', text)
    text = re.sub(r'(?<=\d)\s*\*\s*(?=\d)', ' times ', text)
    for symbol, meaning in (('&', ' and '), ('×', ' times '), ('÷', ' divided by '),
                            ('±', ' plus or minus '), ('≤', ' less than or equal to '),
                            ('≥', ' greater than or equal to '), ('≠', ' not equal to '),
                            ('=', ' equals '), ('+', ' plus ')):
        text = text.replace(symbol, meaning)
    text = text.translate(str.maketrans({'’': "'", '‘': "'", '—': ', ', '–': ', ',
                                        '…': '...', '|': ', ', '(': ', ', ')': ', '}))
    # These marks are formatting, not spoken words. Keep sentence boundaries,
    # decimals, grouping commas, apostrophes and word hyphens for the TTS engine.
    text = text.replace('`', '').replace('*', '').replace('~', '').replace('_', ' ')
    text = ''.join(c if c in ".,!?;:'-\n" or c.isspace() or unicodedata.category(c)[0] not in 'PS'
                   else ' ' for c in text)
    lines = []
    for line in text.split('\n'):
        if not any(c.isalnum() for c in line):
            continue
        line = re.sub(r'\s+([.,!?;:])', r'\1', line)
        line = re.sub(r'^[,;:\s]+|[,;:\s]+$', '', line)
        lines.append(' '.join(line.split()))
    return '\n'.join(lines).strip()
