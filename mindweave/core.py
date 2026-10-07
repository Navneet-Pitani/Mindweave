"""Fusion, conservative safety routing and explicit-feedback adaptation."""
import re
import numpy as np
from mindweave.data import LABELS, VOICE_LABELS

STRATEGIES = ['EMPATHETIC_SUPPORT', 'GROUNDING', 'PROBLEM_SOLVING', 'EXPLORATION']

def align_voice(probabilities):
    # Surprise has no reliable valence: distribute its mass, do not assert Neutral.
    mapping = {'Neutral': 'Neutral', 'Calm': 'Neutral', 'Happy': 'Happy', 'Sad': 'Sad',
               'Angry': 'Angry', 'Fearful': 'Anxiety', 'Disgust': 'Angry'}
    source = validate_distribution(probabilities, 8)
    aligned = np.zeros(5)
    for name, value in zip(VOICE_LABELS, source):
        if name == 'Surprise':
            aligned += value / 5
        else:
            aligned[LABELS.index(mapping[name])] += value
    return aligned

def validate_distribution(values, size=5):
    values = np.asarray(values, dtype=float)
    if values.shape != (size,) or not np.isfinite(values).all() or (values < 0).any() or not np.isclose(values.sum(), 1):
        raise ValueError('Expected a finite, nonnegative probability distribution')
    return values

def fuse(text=None, voice=None, text_quality=1.0, voice_quality=1.0, text_weight=0.5):
    if not all(np.isfinite(x) and 0 <= x <= 1 for x in (text_quality, voice_quality, text_weight)):
        raise ValueError('Weights and qualities must be in [0, 1]')
    numerator, denominator = np.zeros(5), 0.0
    for distribution, weight in ((text, text_quality * text_weight), (voice, voice_quality * (1-text_weight))):
        if distribution is not None:
            numerator += validate_distribution(distribution) * weight
            denominator += weight
    return None if denominator == 0 else numerator / denominator

def safety_route(text):
    """Research rules, not a validated risk classifier. Never use emotion to clear risk."""
    text = text.casefold().replace('’', "'")
    urgent = [r'\b(suicid\w*|kill(?:ing)? myself|hurt(?:ing)? myself|harm(?:ing)? myself|self.harm|want to die)\b',
              r'\b(overdos\w*|end my life)\b', r"(can.t|cannot|don.t think i can).*keep myself safe",
              r'better (off )?(without me|if i)', r"don.t want to (be here|live)",
              r'(not|never) to wake up', r"don.t feel safe.*alone"]
    concerning = [r'\b(hopeless|desperate|disappear forever|giving up)\b',
                  r'nothing matters', r"can.t (do this|see a future)", r'tired of everything',
                  r'scared of what i might do', r'want everything to stop']
    if any(re.search(pattern, text) for pattern in urgent):
        return 'SAFETY_ESCALATION'
    if any(re.search(pattern, text) for pattern in concerning):
        return 'SAFETY_CHECK'
    return 'NORMAL'

def safety_response(route):
    if route == 'SAFETY_ESCALATION':
        return ("I'm sorry you're going through this. Are you in immediate danger or have you already hurt yourself? "
                "If so, contact local emergency services or go to the nearest emergency department now. "
                "If you can, reach out to someone you trust who can stay with you and move away from anything you could use to hurt yourself.")
    return ("That sounds really difficult. When you say that, are you thinking about hurting yourself, or describing how overwhelmed you feel? "
            "If you're in immediate danger, contact local emergency services and someone you trust who can stay with you.")

def choose_strategy(emotion, topic, profile):
    default = {'Anxiety': 'GROUNDING', 'Sad': 'EMPATHETIC_SUPPORT', 'Angry': 'GROUNDING',
               'Happy': 'EXPLORATION', 'Neutral': 'EXPLORATION'}[emotion]
    scores = profile.get(f'{emotion}:{topic}', {})
    return max(STRATEGIES, key=lambda s: scores.get(s, 0.1 if s == default else 0))

def update_profile(profile, emotion, topic, strategy, feedback, learning_rate=0.2):
    if feedback is None:
        return  # missing follow-up is not failure
    if strategy not in STRATEGIES or feedback not in ('helped', 'a_little', 'not_helped'):
        raise ValueError('Invalid strategy or feedback')
    reward = {'helped': 1.0, 'a_little': 0.3, 'not_helped': -1.0}[feedback]
    scores = profile.setdefault(f'{emotion}:{topic}', {})
    old = scores.get(strategy, 0.0)
    scores[strategy] = old + learning_rate * (reward - old)
