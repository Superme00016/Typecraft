"""Validated, data-only typing profiles. Configuration files never execute code."""
from copy import deepcopy
import json
import math
from pathlib import Path
import unicodedata

MAX_RULES = 200
MAX_FILE_BYTES = 512_000


def _number(value, low, high, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{field}: expected a finite number.')
    if not low <= value <= high:
        raise ValueError(f'{field}: must be between {low} and {high}.')
    return float(value)


def _range(value, field):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f'{field}: expected [minimum, maximum] in milliseconds.')
    low, high = [_number(x, 0, 60_000, field) for x in value]
    if low > high:
        raise ValueError(f'{field}: minimum cannot exceed maximum.')
    return [low, high]


def _text(value, field, max_length=80):
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f'{field}: enter 1–{max_length} characters of text.')
    if any(unicodedata.category(c) in ('Cc', 'Cs') for c in value):
        raise ValueError(f'{field}: control characters are not allowed.')
    return value


def _bool(value, field):
    if not isinstance(value, bool):
        raise ValueError(f'{field}: expected true or false.')
    return value


def validate_profile(data):
    if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1:
        raise ValueError('Expected a Typecraft profile with version 1.')
    allowed = {'version', 'name', 'neighbor_errors', 'neighbor_notice_ms',
               'neighbor_backspace_ms', 'neighbor_resume_ms', 'rules'}
    if set(data) - allowed:
        raise ValueError('Unknown profile fields: ' + ', '.join(sorted(set(data) - allowed)))
    result = {'version': 1, 'name': _text(data.get('name'), 'name'),
              'neighbor_errors': _bool(data.get('neighbor_errors', False), 'neighbor_errors')}
    for field, default in [('neighbor_notice_ms', [180, 600]),
                           ('neighbor_backspace_ms', [40, 90]), ('neighbor_resume_ms', [80, 220])]:
        result[field] = _range(data.get(field, default), field)
    entries = data.get('rules', [])
    if not isinstance(entries, list) or len(entries) > MAX_RULES:
        raise ValueError('A profile can contain at most 200 rules.')
    result['rules'] = []
    for index, entry in enumerate(entries):
        prefix = f'rules[{index}]'
        if not isinstance(entry, dict):
            raise ValueError(f'{prefix}: expected an object.')
        kind = entry.get('type')
        if kind not in ('typo', 'pause'):
            raise ValueError(f'{prefix}.type: expected typo or pause.')
        allowed_rule = {'type', 'name', 'match', 'probability', 'enabled', 'wait_ms'}
        if kind == 'typo':
            allowed_rule |= {'replacement', 'correct', 'backspace_ms', 'resume_ms'}
        if set(entry) - allowed_rule:
            raise ValueError(f'{prefix}: unknown fields: ' + ', '.join(sorted(set(entry) - allowed_rule)))
        item = {'type': kind, 'name': _text(entry.get('name'), prefix + '.name'),
                'match': _text(entry.get('match'), prefix + '.match'),
                'probability': _number(entry.get('probability', 1), 0, 1, prefix + '.probability'),
                'enabled': _bool(entry.get('enabled', True), prefix + '.enabled'),
                'wait_ms': _range(entry.get('wait_ms', [250, 650]), prefix + '.wait_ms')}
        if kind == 'typo':
            item['replacement'] = _text(entry.get('replacement'), prefix + '.replacement')
            if item['replacement'] == item['match']:
                raise ValueError(f'{prefix}: replacement must differ from the original text.')
            if any(ord(c) > 0xffff or unicodedata.category(c).startswith('M') or
                   unicodedata.category(c) == 'Cf' for c in item['match'] + item['replacement']):
                raise ValueError('Typo rules cannot contain emoji, combining marks, or invisible formatting characters.')
            item['correct'] = _bool(entry.get('correct', True), prefix + '.correct')
            item['backspace_ms'] = _range(entry.get('backspace_ms', [40, 90]), prefix + '.backspace_ms')
            item['resume_ms'] = _range(entry.get('resume_ms', [80, 220]), prefix + '.resume_ms')
        result['rules'].append(item)
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field: ' + key)
        result[key] = value
    return result


def load_profile(path):
    with Path(path).open('rb') as handle:
        raw = handle.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError('The configuration file is too large (maximum 512 KB).')
    try:
        data = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_unique_object)
    except RecursionError as exc:
        raise ValueError('The configuration is nested too deeply.') from exc
    return validate_profile(data)


def save_profile(path, profile):
    validated = validate_profile(profile)
    Path(path).write_text(json.dumps(validated, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def typo(name, match, replacement, probability=.08):
    return {'type': 'typo', 'name': name, 'match': match, 'replacement': replacement,
            'probability': probability, 'enabled': True, 'correct': True,
            'wait_ms': [300, 850], 'backspace_ms': [45, 100], 'resume_ms': [90, 240]}


BUILTINS = {
    'english': validate_profile({
        'version': 1, 'name': 'English · nearby keys', 'neighbor_errors': True,
        'rules': [typo('Letter order', 'the', 'teh', .06),
                  {'type': 'pause', 'name': 'Sentence pause', 'match': '.', 'probability': .4,
                   'wait_ms': [250, 750]}],
    }),
    'chinese': validate_profile({
        'version': 1, 'name': '中文 · 同音错字', 'neighbor_errors': False,
        'rules': [typo('的／得', '的', '得', .06), typo('在／再', '在', '再', .06),
                  typo('你好／你号', '你好', '你号', .1),
                  {'type': 'pause', 'name': '句号停顿', 'match': '。', 'probability': .5,
                   'wait_ms': [300, 850]},
                  {'type': 'pause', 'name': '逗号停顿', 'match': '，', 'probability': .3,
                   'wait_ms': [150, 400]}],
    }),
}


def builtin(name):
    return deepcopy(BUILTINS[name])
