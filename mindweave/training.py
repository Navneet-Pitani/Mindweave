"""Shared validation selection and final held-out reporting."""
import json
from pathlib import Path
import joblib
import numpy as np
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

def metrics(y, prediction, labels):
    return {'accuracy': accuracy_score(y, prediction),
            'macro_f1': f1_score(y, prediction, labels=labels, average='macro', zero_division=0),
            'per_class': classification_report(y, prediction, labels=labels, output_dict=True, zero_division=0),
            'confusion_matrix': confusion_matrix(y, prediction, labels=labels).tolist()}

def select(candidates, train, dev, test, labels, output, metadata):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    results, best, best_score, best_name = {}, None, -1, None
    for name, model in candidates.items():
        print(f'Training {name}', flush=True)
        model.fit(*train)
        result = metrics(dev[1], model.predict(dev[0]), labels)
        results[name] = result
        print(f'  validation macro-F1: {result["macro_f1"]:.4f}', flush=True)
        if result['macro_f1'] > best_score:
            best, best_score, best_name = model, result['macro_f1'], name
    report = {'selected': best_name, 'label_order': labels, 'validation': results,
              'test': metrics(test[1], best.predict(test[0]), labels), 'metadata': metadata}
    joblib.dump(best, output / 'model.joblib')
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'Selected {best_name}; test macro-F1 {report["test"]["macro_f1"]:.4f}', flush=True)
    return best, report

def probabilities(model, inputs, labels):
    raw = model.predict_proba(inputs)[0]
    return np.array([raw[list(model.classes_).index(label)] if label in model.classes_ else 0.0 for label in labels])
