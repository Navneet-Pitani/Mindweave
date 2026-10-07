"""Train five-class text baselines: python -m goemotions_5class_model.train_improved."""
import argparse
from sklearn.pipeline import make_pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import ComplementNB
from sklearn.calibration import CalibratedClassifierCV
from sklearn.svm import LinearSVC
from mindweave.data import LABELS, GO_MAP, load_goemotions
from mindweave.training import select

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default='data/goemotions')
    parser.add_argument('--output-dir', default='artifacts/text')
    args = parser.parse_args()
    splits, audit = load_goemotions(args.data_dir)
    estimators = {
        'naive_bayes': ComplementNB(alpha=0.5),
        'logistic_regression': LogisticRegression(C=3, max_iter=1000, class_weight='balanced', random_state=42),
        'linear_svm': CalibratedClassifierCV(LinearSVC(C=1, class_weight='balanced', random_state=42), cv=3),
    }
    candidates = {name: make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=50000, sublinear_tf=True), model) for name, model in estimators.items()}
    select(candidates, splits['train'], splits['dev'], splits['test'], LABELS, args.output_dir,
           {'data': audit, 'ontology': GO_MAP, 'seed': 42, 'calibration': 'SVM internal training-only 3-fold calibration'})

if __name__ == '__main__':
    main()
