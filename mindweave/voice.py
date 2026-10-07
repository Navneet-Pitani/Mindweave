"""RAVDESS features and reproducible actor-disjoint baseline comparison."""
import argparse
from pathlib import Path
import numpy as np
import librosa
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from mindweave.data import VOICE_LABELS
from mindweave.training import select

def features(path):
    y, sr = librosa.load(path, sr=16000, mono=True)
    if len(y) < 2048 or not np.isfinite(y).all() or np.max(np.abs(y)) < 1e-6:
        raise ValueError(f'Audio is too short, silent, or invalid: {path}')
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
    frames = np.vstack([mfcc, librosa.feature.delta(mfcc, mode='nearest'),
                        librosa.feature.delta(mfcc, order=2, mode='nearest'),
                        librosa.feature.spectral_centroid(y=y, sr=sr),
                        librosa.feature.spectral_bandwidth(y=y, sr=sr),
                        librosa.feature.spectral_rolloff(y=y, sr=sr),
                        librosa.feature.zero_crossing_rate(y), librosa.feature.rms(y=y)])
    return np.concatenate([frames.mean(axis=1), frames.std(axis=1)])

def actor_split(actor):
    # Each held-out group contains two female and two male speakers.
    return 'test' if actor in (21, 22, 23, 24) else 'dev' if actor in (17, 18, 19, 20) else 'train'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actors-dir', default='Actors')
    parser.add_argument('--output-dir', default='artifacts/voice')
    args = parser.parse_args()
    splits = {s: ([], []) for s in ('train', 'dev', 'test')}
    actors = {s: set() for s in splits}
    manifest = []
    paths = sorted(Path(args.actors_dir).rglob('*.wav'))
    for i, path in enumerate(paths):
        fields = list(map(int, path.stem.split('-')))
        if len(fields) != 7 or fields[0:2] != [3, 1]:
            continue  # speech-only audio
        actor, emotion = fields[6], fields[2]
        if not 1 <= actor <= 24 or not 1 <= emotion <= 8:
            raise ValueError(f'Invalid RAVDESS filename: {path}')
        split = actor_split(actor)
        splits[split][0].append(features(path))
        splits[split][1].append(VOICE_LABELS[emotion - 1])
        actors[split].add(actor)
        manifest.append({'file': str(path), 'actor': actor, 'split': split})
        if i % 100 == 0:
            print(f'Extracted {i + 1}/{len(paths)}', flush=True)
    if any(not data[0] for data in splits.values()):
        raise ValueError('Need RAVDESS speech audio in all three actor groups')
    candidates = {
        'random_forest': RandomForestClassifier(n_estimators=250, class_weight='balanced', n_jobs=-1, random_state=42),
        'extra_trees': ExtraTreesClassifier(n_estimators=250, class_weight='balanced', n_jobs=-1, random_state=42),
        'rbf_svm': make_pipeline(StandardScaler(), SVC(C=10, probability=True, class_weight='balanced', random_state=42)),
    }
    select(candidates, splits['train'], splits['dev'], splits['test'], VOICE_LABELS, args.output_dir,
           {'actors': {s: sorted(a) for s, a in actors.items()}, 'manifest': manifest, 'sample_rate': 16000, 'features': '20 MFCC + delta + delta2 + 5 spectral/energy features; mean and std', 'seed': 42})

if __name__ == '__main__':
    main()
