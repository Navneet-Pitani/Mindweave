"""Explicit ontology and leakage-aware data loading."""
import csv
import re
from collections import Counter
from pathlib import Path

LABELS = ['Happy', 'Sad', 'Angry', 'Anxiety', 'Neutral']
GO_LABELS = 'admiration amusement anger annoyance approval caring confusion curiosity desire disappointment disapproval disgust embarrassment excitement fear gratitude grief joy love nervousness optimism pride realization relief remorse sadness surprise neutral'.split()
GROUPS = {
    'Happy': 'admiration amusement approval caring desire excitement gratitude joy love optimism pride relief'.split(),
    'Sad': 'disappointment grief remorse sadness embarrassment'.split(),
    'Angry': 'anger annoyance disapproval disgust'.split(),
    'Anxiety': 'fear nervousness'.split(),
    'Neutral': 'confusion curiosity realization surprise neutral'.split(),
}
GO_MAP = {name: target for target, names in GROUPS.items() for name in names}
VOICE_LABELS = ['Neutral', 'Calm', 'Happy', 'Sad', 'Angry', 'Fearful', 'Disgust', 'Surprise']

def key(text):
    return re.sub(r'\s+', ' ', text.casefold()).strip()

def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def load_goemotions(directory):
    """Keep only annotations agreeing in the coarse ontology; remove cross-split duplicates.

    Test and dev reserve their texts first so training cannot contain held-out text.
    Ambiguous multi-label rows are dropped rather than assigned an arbitrary class.
    """
    result, audit, seen = {}, {}, set()
    for split in ('test', 'dev', 'train'):
        texts, labels = [], []
        counts = Counter()
        with (Path(directory) / f'{split}.tsv').open(encoding='utf-8', newline='') as f:
            for text, ids, _ in csv.reader(f, delimiter='\t'):
                normalized = key(text)
                targets = {GO_MAP[GO_LABELS[int(i)]] for i in ids.split(',')}
                if normalized in seen or not normalized:
                    counts['duplicate_or_empty'] += 1
                    continue
                seen.add(normalized)
                if len(targets) != 1:
                    counts['ambiguous'] += 1
                    continue
                texts.append(text)
                labels.append(targets.pop())
        counts.update({'kept': len(texts)})
        result[split] = (texts, labels)
        audit[split] = dict(counts, classes=dict(Counter(labels)))
    return result, audit
