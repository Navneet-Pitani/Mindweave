import numpy as np
import pytest
from cryptography.fernet import Fernet
from mindweave.core import align_voice, fuse, safety_route, update_profile, choose_strategy
from mindweave.storage import Store
from mindweave.voice import actor_split
from mindweave.data import load_goemotions

def test_missing_modality_is_not_neutral():
    p = [0.1, 0.7, 0.1, 0.05, 0.05]
    np.testing.assert_allclose(fuse(text=p), p)
    assert fuse() is None
    assert fuse(text=p, text_quality=0) is None
    np.testing.assert_allclose(fuse(text=p, voice=[1,0,0,0,0], voice_quality=0), p)

def test_alignment_and_invalid_inputs():
    np.testing.assert_allclose(align_voice([0,0,0,0,0,1,0,0]), [0,0,0,1,0])
    np.testing.assert_allclose(align_voice([0,0,0,0,0,0,0,1]), [0.2]*5)
    with pytest.raises(ValueError):
        fuse(text=[float('nan')]*5)
    with pytest.raises(ValueError):
        fuse(text_weight=-1)

def test_safety_precedes_support_and_slang_is_not_automatically_crisis():
    assert safety_route('I want to kill myself') == 'SAFETY_ESCALATION'
    assert safety_route('I am thinking about killing myself') == 'SAFETY_ESCALATION'
    assert safety_route('I feel hopeless') == 'SAFETY_CHECK'
    assert safety_route("I'm cooked bro") == 'NORMAL'

def test_user_preferences_diverge_and_missing_feedback_does_not_update():
    a, b = {}, {}
    update_profile(a, 'Anxiety', 'exam', 'GROUNDING', None)
    assert a == {}
    update_profile(a, 'Anxiety', 'exam', 'GROUNDING', 'not_helped')
    assert choose_strategy('Anxiety', 'exam', a) != choose_strategy('Anxiety', 'exam', b)

def test_encrypted_isolated_storage_and_deletion(tmp_path, monkeypatch):
    monkeypatch.setenv('MINDWEAVE_KEY', Fernet.generate_key().decode())
    a, b = Store(tmp_path, 'alice'), Store(tmp_path, 'bob')
    a.save({'secret': 'private message'})
    assert b.load()['memories'] == {}
    assert b'private message' not in a.path.read_bytes()
    assert a.load()['secret'] == 'private message'
    a.delete()
    assert not a.path.exists()

def test_actor_groups_are_disjoint():
    groups = {s: {a for a in range(1,25) if actor_split(a)==s} for s in ('train','dev','test')}
    assert [len(groups[s]) for s in ('train','dev','test')] == [16,4,4]
    assert not groups['train'] & groups['test']

def test_text_loader_drops_conflicting_labels_and_leakage(tmp_path):
    (tmp_path/'test.tsv').write_text('held out\t17\t1\n', encoding='utf-8')
    (tmp_path/'dev.tsv').write_text('validation\t25\t2\n', encoding='utf-8')
    (tmp_path/'train.tsv').write_text('held out\t17\t3\nambiguous\t17,25\t4\ngood\t17,0\t5\n', encoding='utf-8')
    splits, audit = load_goemotions(tmp_path)
    assert splits['train'] == (['good'], ['Happy'])
    assert audit['train']['ambiguous'] == 1
