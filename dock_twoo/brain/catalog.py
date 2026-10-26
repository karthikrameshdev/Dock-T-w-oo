"""Packaged character identities and their artist-authored animation libraries."""
from functools import lru_cache
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1] / 'server' / 'static' / 'brain3d'

@lru_cache(maxsize=1)
def characters():
    return tuple(json.loads((ROOT / 'catalog.json').read_text(encoding='utf-8'))['characters'])

@lru_cache(maxsize=32)
def character(character_id='default'):
    entry = next((c for c in characters() if c['id'] == character_id), None)
    if entry is None:
        raise ValueError('Unknown assistant character: ' + str(character_id))
    return {**entry, **json.loads((ROOT / entry['manifest']).read_text(encoding='utf-8'))}

def named_prefix(text, *, acoustic=False):
    """Only a leading name addresses an assistant; mentioning a name is not a wake."""
    names = {c['name'].casefold(): c['id'] for c in characters()}
    names.update({'brian': 'default', 'buddy': 'default'})
    pattern = '|'.join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    if acoustic:
        text = re.sub(r'^\s*(?:hay|hei)(?=[\s,])', 'Hey', text, flags=re.I)
    match = re.match(r'^\s*(?:(?:hey|hello|hi|okay|ok|yo)[\s,.:;!?…–—-]+)?(' + pattern + r')\b[\s,.:;!?…–—-]*', text, re.I)
    if match:
        return names[match[1].casefold()], text[match.end():].strip()
    if acoustic:
        # Observed local-ASR phonetic spellings, only after an explicit greeting.
        aliases = {'tucks':'tuxedo', 'talks':'tuxedo', 'tox':'tuxedo', 'machai':'siamese', 'mochi':'siamese',
                   'bow':'panda', 'ramai':'rat', 'remi':'rat', 'safran':'chef', 'saffran':'chef',
                   'suri':'musician', 'yury':'musician'}
        pattern = '|'.join(aliases)
        text = re.sub(r'^\s*(hey|hay|hello|hi)(?=(?:'+pattern+r')\b)', r'\1 ', text, flags=re.I)
        heard = re.match(r'^\s*(?:hey|hello|hi|hay)[\s,.:;!?…–—-]+('+pattern+r')\b[\s,.:;!?…–—-]*', text, re.I)
        if heard:
            return aliases[heard[1].casefold()], text[heard.end():].strip()
        compact = re.match(r'^\s*(?:heikai|haikai|hey\s+kai|hayes-yury)\b[\s,.:;!?…–—-]*', text, re.I)
        if compact:
            return ('musician' if compact[0].strip().lower().startswith('hayes') else 'explorer'), text[compact.end():].strip()
    return None, text.strip()

def keyword_id(keyword):
    return next((c['id'] for c in characters() if c['name'].casefold() == keyword.replace('_', ' ').casefold()),
                'default' if keyword.upper() in ('BRAIN', 'BUDDY', 'BRIAN') else None)

def actions_for(character_id):
    return {key: (value.get('description', key.replace('_', ' ').title()), value['duration'])
            for key, value in character(character_id)['actions'].items()}
