"""Typing plans. Pure Python; no GUI or keyboard permissions required."""
from dataclasses import dataclass
import math
import random


# Nearby keys on a QWERTY keyboard. Only ASCII letters receive deliberate errors.
NEIGHBORS = {
    'q': 'wa', 'w': 'qase', 'e': 'wsdr', 'r': 'edft', 't': 'rfgy',
    'y': 'tghu', 'u': 'yhji', 'i': 'ujko', 'o': 'iklp', 'p': 'ol',
    'a': 'qwsz', 's': 'awedxz', 'd': 'serfcx', 'f': 'drtgvc',
    'g': 'ftyhbv', 'h': 'gyujnb', 'j': 'huikmn', 'k': 'jiolm',
    'l': 'kop', 'z': 'asx', 'x': 'zsdc', 'c': 'xdfv', 'v': 'cfgb',
    'b': 'vghn', 'n': 'bhjm', 'm': 'njk',
}
MAX_CHARACTERS = 100_000


@dataclass(frozen=True)
class Stroke:
    kind: str  # insert, backspace, or wait
    text: str
    delay: float  # seconds BEFORE this stroke
    completed: int  # number of source characters correctly entered
    typo: bool = False
    fixed_delay: float = 0.0
    mistake_start: bool = False


@dataclass(frozen=True)
class Plan:
    strokes: tuple[Stroke, ...]
    duration: float
    characters: int
    mistakes: int
    extra_wait: float = 0.0
    corrected: int = 0
    retained: int = 0


def normalized_text(text: str) -> str:
    return text.replace('\r\n', '\n').replace('\r', '\n')


def duration_for(text: str, mode: str, value: float) -> float:
    """A standard typing word is five characters, including spaces."""
    if not math.isfinite(value) or value <= 0:
        raise ValueError('Enter a positive, finite speed or duration.')
    if mode == 'minutes':
        return value * 60
    if mode == 'wps':
        return len(normalized_text(text)) / (value * 5)
    raise ValueError('Unknown speed mode.')


def make_plan(text: str, duration: float, error_rate: float = .02,
              variation: float = .55, seed: int | None = None, profile=None) -> Plan:
    text = normalized_text(text)
    if not text.strip():
        raise ValueError('Paste or type some text first.')
    if len(text) > MAX_CHARACTERS:
        raise ValueError(f'Please use at most {MAX_CHARACTERS:,} characters per run.')
    if not math.isfinite(duration) or duration <= 0 or duration > 86400:
        raise ValueError('Choose a duration greater than zero and no longer than 24 hours.')
    if not 0 <= error_rate <= .15 or not 0 <= variation <= 1:
        raise ValueError('Invalid mistake rate or rhythm setting.')
    if any(ord(c) < 32 and c not in '\n\t' or ord(c) == 127 for c in text):
        raise ValueError('The text contains control characters. Remove them before typing.')
    if profile is not None:
        return _custom_plan(text, duration, error_rate, variation, seed, profile)
    rng = random.Random(seed)
    raw = []
    mistakes = 0
    for i, char in enumerate(text):
        weight = rng.lognormvariate(0, .65 * variation)
        if i:
            previous = text[i - 1]
            if previous in '.!?。！？':
                weight += 3.2 * variation
            elif previous in ',;:，；：':
                weight += 1.4 * variation
            elif previous == '\n':
                weight += 4 * variation
            elif previous == ' ':
                weight += .6 * variation
            if rng.random() < .015 * variation:
                weight += rng.uniform(2, 5) * variation
        if char.lower() in NEIGHBORS and rng.random() < error_rate:
            wrong = rng.choice(NEIGHBORS[char.lower()])
            if char.isupper():
                wrong = wrong.upper()
            raw.append(Stroke('insert', wrong, weight, i, True))
            raw.append(Stroke('backspace', '', rng.uniform(1.4, 2.8), i))
            weight = rng.uniform(.6, 1.1)
            mistakes += 1
        raw.append(Stroke('insert', char, weight, i + 1))
    factor = duration / sum(stroke.delay for stroke in raw)
    strokes = tuple(Stroke(s.kind, s.text, s.delay * factor, s.completed, s.typo)
                    for s in raw)
    return Plan(strokes, duration, len(text), mistakes, corrected=mistakes)


def _custom_plan(text, duration, error_rate, variation, seed, profile):
    from rules import validate_profile
    profile = validate_profile(profile)
    rng = random.Random(seed)
    raw = []
    corrected = retained = 0
    candidates, pauses = {}, {}
    for rule in profile['rules']:
        if not rule['enabled']:
            continue
        if rule['type'] == 'typo':
            candidates.setdefault(rule['match'][0], []).append(rule)
        else:
            pauses.setdefault(rule['match'][-1], []).append(rule)
    for group in candidates.values():
        group.sort(key=lambda rule: -len(rule['match']))

    def seconds(bounds):
        return rng.uniform(*bounds) / 1000

    def weight(previous=''):
        value = rng.lognormvariate(0, .65 * variation)
        if previous:
            if previous in '.!?。！？':
                value += 3.2 * variation
            elif previous in ',;:，；：':
                value += 1.4 * variation
            elif previous == '\n':
                value += 4 * variation
            elif previous == ' ':
                value += .6 * variation
        if rng.random() < .015 * variation:
            value += rng.uniform(2, 5) * variation
        return value

    def push(kind, char, completed, previous='', typo=False, fixed=0, first=False):
        if len(raw) >= 500_000:
            raise ValueError('These rules generate too many keystrokes. Use shorter text or fewer rules.')
        raw.append(Stroke(kind, char, 0 if kind == 'wait' else weight(previous),
                          completed, typo, fixed, first))

    i = 0
    while i < len(text):
        start = i
        selected = next((rule for rule in candidates.get(text[i], [])
                         if text.startswith(rule['match'], i)), None)
        if selected is None and profile['neighbor_errors'] and text[i].lower() in NEIGHBORS:
            if rng.random() < error_rate:
                wrong = rng.choice(NEIGHBORS[text[i].lower()])
                if text[i].isupper():
                    wrong = wrong.upper()
                selected = {'match': text[i], 'replacement': wrong, 'probability': 1,
                            'correct': True, 'wait_ms': profile['neighbor_notice_ms'],
                            'backspace_ms': profile['neighbor_backspace_ms'],
                            'resume_ms': profile['neighbor_resume_ms']}
        match = selected['match'] if selected else text[i]
        end = i + len(match)
        if selected and rng.random() < selected['probability']:
            wrong = selected['replacement']
            correct = selected['correct']
            for j, char in enumerate(wrong):
                completed = end if not correct and j == len(wrong) - 1 else i
                push('insert', char, completed, text[i - 1] if i and not j else '',
                     typo=True, first=j == 0)
            push('wait', '', i if correct else end, fixed=seconds(selected['wait_ms']))
            if correct:
                for _ in wrong:
                    push('backspace', '', i, fixed=seconds(selected['backspace_ms']))
                for j, char in enumerate(match):
                    push('insert', char, i + j + 1,
                         fixed=seconds(selected['resume_ms']) if j == 0 else 0)
                corrected += 1
            else:
                retained += 1
        else:
            for j, char in enumerate(match):
                push('insert', char, i + j + 1, text[i + j - 1] if i + j else '')
        i = end
        for position in range(start + 1, end + 1):
            for rule in pauses.get(text[position - 1], []):
                if text.endswith(rule['match'], 0, position) and rng.random() < rule['probability']:
                    push('wait', '', end, fixed=seconds(rule['wait_ms']))
    extra = sum(s.fixed_delay for s in raw)
    if duration + extra > 86400:
        raise ValueError('Typing plus rule delays exceeds 24 hours. Use shorter text or shorter waits.')
    factor = duration / sum(s.delay for s in raw)
    strokes = tuple(Stroke(s.kind, s.text, s.delay * factor + s.fixed_delay,
                           s.completed, s.typo, s.fixed_delay, s.mistake_start) for s in raw)
    return Plan(strokes, duration + extra, len(text), corrected + retained, extra, corrected, retained)


def format_time(seconds: float) -> str:
    seconds = max(0, math.ceil(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f'{hours}:{minutes:02}:{seconds:02}' if hours else f'{minutes}:{seconds:02}'
