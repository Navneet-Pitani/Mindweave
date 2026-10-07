"""Interactive local support demo; type /help for feedback and privacy commands."""
import argparse
from datetime import datetime, timezone
import json
import joblib
from mindweave.core import align_voice, fuse, safety_route, safety_response, choose_strategy, update_profile
from mindweave.data import LABELS, VOICE_LABELS
from mindweave.responses import retrieve, context
from mindweave.training import probabilities
from mindweave.storage import Store

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--text-model', default='artifacts/text/model.joblib')
    p.add_argument('--responses', default='artifacts/responses.joblib')
    p.add_argument('--voice-model', default='artifacts/voice/model.joblib')
    p.add_argument('--user-id', default='local')
    p.add_argument('--persist', action='store_true', help='Opt in to encrypted local observations and explicit memories')
    args = p.parse_args()
    model, responses = joblib.load(args.text_model), joblib.load(args.responses)
    store = Store('private', args.user_id) if args.persist else None
    state = store.load() if store else {'profile': {}, 'memories': {}, 'observations': []}
    pending, voice = None, None
    print('MINDWEAVE research demo. /help for commands. No diagnosis. Persistence:', bool(store))
    while True:
        try:
            message = input('You: ').strip()
        except (EOFError, KeyboardInterrupt):
            break
        if message == '/quit':
            break
        if not message:
            continue
        if message == '/help':
            print('/feedback helped|a_little|not_helped; /voice PATH (next message); /remember KEY=VALUE; /forget KEY; /memories; /report; /delete; /quit')
            continue
        if message.startswith('/feedback '):
            if pending is None:
                print('No ordinary intervention awaiting feedback.')
                continue
            try:
                update_profile(state['profile'], *pending, message.split(maxsplit=1)[1])
            except ValueError as error:
                print(error)
                continue
            pending = None
        elif message.startswith('/voice '):
            from mindweave.voice import features
            try:
                voice = align_voice(probabilities(joblib.load(args.voice_model), [features(message[7:].strip('"'))], VOICE_LABELS))
                print('Voice loaded for the next message. Acoustic quality is not calibrated.')
            except (ValueError, OSError) as error:
                voice = None
                print(error)
            continue
        elif message.startswith('/remember '):
            k, separator, value = message[10:].partition('=')
            if not separator or not k.strip():
                print('Use /remember KEY=VALUE')
                continue
            state['memories'][k.strip()] = value.strip()
        elif message.startswith('/forget '):
            state['memories'].pop(message[8:], None)
        elif message == '/memories':
            print(json.dumps(state['memories'], indent=2))
        elif message == '/report':
            from collections import Counter
            print(json.dumps({'observations': len(state['observations']), 'estimated_emotions': dict(Counter(x['emotion'] for x in state['observations'])), 'preferences': state['profile']}, indent=2))
        elif message == '/delete':
            state = {'profile': {}, 'memories': {}, 'observations': []}
            pending, voice = None, None
            if store:
                store.delete()
            print('Local profile cleared.')
            continue
        elif message.startswith('/'):
            print('Unknown command. Use /help.')
            continue
        else:
            pending = None
            route = safety_route(message)
            if route != 'NORMAL':
                voice = None
                print(f'MINDWEAVE [{route}]: {safety_response(route)}')
                continue
            distribution = fuse(probabilities(model, [message], LABELS), voice)
            voice = None
            emotion = LABELS[int(distribution.argmax())]
            topic, stress = context(responses, message)
            strategy = choose_strategy(emotion, topic, state['profile'])
            response, source = retrieve(responses, message, emotion, strategy)
            print(f'MINDWEAVE: {response}')
            print(f'[estimate: {emotion}; stress proxy: {stress}; strategy: {strategy}; confidence: {max(distribution):.2f}; source: {source or "template"}]')
            pending = (emotion, topic, strategy)
            state['observations'].append({'time': datetime.now(timezone.utc).isoformat(), 'emotion': emotion, 'stress': stress, 'strategy': strategy})
        if store:
            store.save(state)

if __name__ == '__main__':
    main()
