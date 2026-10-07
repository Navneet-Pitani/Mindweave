"""A retrieval baseline; 240 examples are not sufficient for a fluent generator from scratch."""
import argparse
import re
from pathlib import Path
import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from mindweave.data import read_csv, key
from mindweave.core import STRATEGIES

FALLBACK = {
    'EMPATHETIC_SUPPORT': 'That sounds difficult. What part of this is weighing on you most?',
    'GROUNDING': 'Would it help to pause and notice a few things you can see and feel around you?',
    'PROBLEM_SOLVING': 'What is one small, manageable step you could take next?',
    'EXPLORATION': 'Could you tell me a little more about what this has been like for you?',
}

def build(path, output):
    rows, seen = [], set()
    for row in read_csv(path):
        signature = key(row['user_message'])
        if signature in seen or row['safety_level'] != 'low':
            continue
        if row['intervention'] not in STRATEGIES:
            raise ValueError('Unknown intervention')
        seen.add(signature)
        rows.append(row)
    if not rows:
        raise ValueError('No low-risk response examples')
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
    matrix = vectorizer.fit_transform([r['user_message'] for r in rows])
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({'rows': rows, 'vectorizer': vectorizer, 'matrix': matrix}, output)
    print(f'Indexed {len(rows)} unique training messages')

TOPIC_WORDS = {
    'exam': r'\b(exam|exams|test|tests|studying|revision)\b',
    'assignment': r'\b(assignment|assignments|deadline|deadlines|homework)\b',
    'sleep': r'\b(sleep|sleeping|insomnia|awake)\b',
    'breakup': r'\b(breakup|broke up|ex|dumped)\b',
    'friendship': r'\b(friend|friends|friendship)\b',
    'job': r'\b(job|internship|internships|rejected|placement)\b',
    'loneliness': r'\b(lonely|loneliness|isolated)\b',
    'burnout': r'\b(burnout|burned out|burnt out|exhausted)\b',
}
TOPIC_PROMPTS = {
    'exam': ['Is the hardest part preparing, the pressure to do well, or something that happened in an exam?', 'What is the next exam task you need to tackle? We can make that one step smaller.', 'Would you rather talk about the pressure or make a short study plan?'],
    'assignment': ['Which deadline is closest, and what is left to do for it?', 'What is one part of the assignment you could finish without trying to solve the whole thing?', 'Is the workload itself the problem, or is it hard to get started?'],
    'sleep': ['What usually happens when you try to settle down for the night?', 'Are thoughts keeping you awake, or is something else interrupting your sleep?', 'Would you like to talk through what is on your mind before thinking about a routine?'],
    'breakup': ['What has been hardest since the relationship ended?', 'Do you miss the person, the routine you shared, or both?', 'Would talking about what happened help more than advice right now?'],
    'friendship': ['What happened with your friend, and how did you take it?', 'What would you want your friend to understand about your side of this?', 'Are you hoping to reconnect, set a boundary, or just talk it through?'],
    'job': ['Which part of the job search is weighing on you: finding roles, applying, or interviews?', 'What happened with the most recent opportunity?', 'Would it help to focus on one application step you can control today?'],
    'loneliness': ['When do you notice the loneliness most?', 'Is there someone you feel comfortable being yourself around, even a little?', 'Are you missing company, or the feeling of being understood?'],
    'burnout': ['What has been using up most of your energy lately?', 'Is there anything on your plate that could be postponed or made smaller?', 'What kind of rest feels possible today, even briefly?'],
}

def detect_topic(message):
    return next((topic for topic, pattern in TOPIC_WORDS.items() if re.search(pattern, message, re.I)), None)

def retrieve(bundle, message, emotion, strategy, history=None, topic=None):
    history = history or []
    recent = {key(t['result']['response']) for t in history[-8:]}
    lowered = key(message)
    if re.fullmatch(r'(hi|hey|hello|hiya)[!. ]*', lowered):
        return 'Hey. What would you like to talk about today?', 'dialogue:greeting'
    if re.search(r'\b(same (response|thing)|repeating|repetitive|not listening|you don.t understand)\b', lowered):
        return "You're right to point that out. My earlier reply didn't address what you needed. What did I miss, or would you prefer a concrete next step instead of another question?", 'dialogue:repair'
    if re.fullmatch(r'(thanks|thank you|ty)[!. ]*', lowered):
        return 'You’re welcome. We can keep talking, or leave it here for now.', 'dialogue:thanks'
    topic = detect_topic(message) or topic
    # Recent topic informs short follow-ups; it does not overwrite a new explicit topic.
    query = message
    if history and len(message.split()) <= 5 and not detect_topic(message):
        query += ' ' + history[-1]['message']
        topic = topic if topic and topic != 'unknown' else history[-1]['result'].get('topic')
    similarity = (bundle['matrix'] @ bundle['vectorizer'].transform([query]).T).toarray().ravel()
    candidates = [i for i, r in enumerate(bundle['rows']) if key(r['response']) not in recent and similarity[i] >= 0.25]
    if candidates:
        # Emotion is a soft signal; an incorrect Neutral estimate must not discard an exact exam match.
        i = max(candidates, key=lambda j: similarity[j] + 0.06 * (bundle['rows'][j]['intervention'] == strategy)
                + 0.03 * (bundle['rows'][j]['emotion'] == emotion) + 0.05 * (bundle['rows'][j]['topic'] == topic))
        row = bundle['rows'][i]
        return row['response'].replace('\ufffd', ' — '), row['id']
    options = TOPIC_PROMPTS.get(topic, [])
    if not options:
        options = (['What feels different about today compared with your usual day?', 'Would you prefer to talk it through, or look for a practical next step?', 'What would be most useful for you from this conversation right now?']
                   if history else ['What happened that brought this feeling up?', 'Would you like to tell me what happened, or focus on what to do next?'])
    available = [p for p in options if key(p) not in recent]
    if available:
        return available[0], 'template:' + (topic or 'clarify')
    return 'I’m running out of useful matches in this small response library. Could you describe one specific part you would like help with?', 'template:limit'

def context(bundle, message):
    similarity = (bundle['matrix'] @ bundle['vectorizer'].transform([message]).T).toarray().ravel()
    i = int(np.argmax(similarity))
    if similarity[i] < 0.3:
        return detect_topic(message) or 'unknown', 'Unknown'
    return bundle['rows'][i]['topic'], bundle['rows'][i]['stress']

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', default='data/custom/mindweave_response_training_240.csv')
    parser.add_argument('--output', default='artifacts/responses.joblib')
    args = parser.parse_args()
    build(args.data, args.output)
