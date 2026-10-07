"""Evaluate held-out custom cases without fitting or tuning on them."""
import argparse
import csv
import json
from pathlib import Path
import joblib
from mindweave.core import safety_route, choose_strategy
from mindweave.data import read_csv
from mindweave.responses import retrieve, context

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default='data/custom')
    parser.add_argument('--output-dir', default='artifacts/evaluation')
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows = read_csv(Path(args.data_dir) / 'mindweave_safety_evaluation_100.csv')
    for row in rows:
        row['predicted_route'] = safety_route(row['input_text'])
    def summary(items):
        high = [r for r in items if r['risk_level'] in ('high', 'critical')]
        return {'cases': len(items), 'exact_route_accuracy': sum(r['predicted_route'] == r['expected_route'] for r in items)/len(items),
                'bypass_recall': sum(r['predicted_route'] != 'NORMAL' for r in items)/len(items),
                'high_risk_bypass_recall': sum(r['predicted_route'] != 'NORMAL' for r in high)/len(high),
                'misses': [r['id'] for r in items if r['predicted_route'] == 'NORMAL']}
    unique = list({r['input_text']: r for r in rows}.values())
    report = {'evaluation_status': 'Development regression: this set exposed a verb-inflection bug subsequently repaired; not an untouched test',
              'all_rows': summary(rows), 'unique_messages': summary(unique),
              'limitations': ['All supplied safety cases require bypass. Specificity cannot be estimated from these cases.',
                              'Rules are unvalidated and may miss indirect risk or overreact to negation/quotation.',
                              'No verified regional resource directory is configured. Deployment requires one.']}
    # Ordinary response-training data is a diagnostic negative set, not an independent safety test.
    negatives = read_csv(Path(args.data_dir) / 'mindweave_response_training_240.csv')
    report['training_negative_diagnostic'] = {'cases': len(negatives), 'flagged': sum(safety_route(r['user_message']) != 'NORMAL' for r in negatives)}
    (output / 'safety_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    with (output / 'safety_predictions.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    model, bundle = joblib.load('artifacts/text/model.joblib'), joblib.load('artifacts/responses.joblib')
    slang = read_csv(Path(args.data_dir) / 'mindweave_genz_slang_test_100.csv')
    for row in slang:
        message = row['input_text']
        emotion = model.predict([message])[0]
        topic, stress = context(bundle, message)
        strategy = choose_strategy(emotion, topic, {})
        row.update(predicted_emotion=emotion, predicted_topic=topic, stress_proxy=stress,
                   route=safety_route(message), response=retrieve(bundle, message, emotion, strategy)[0],
                   human_interpretation_correct='', human_empathy_1_to_5='', human_safety_pass='')
    with (output / 'slang_human_review.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(slang[0])); writer.writeheader(); writer.writerows(slang)
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
