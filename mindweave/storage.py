"""Opt-in encrypted local storage. Identity is a local profile, not authentication."""
import hashlib
import json
import os
from pathlib import Path
from cryptography.fernet import Fernet

class Store:
    def __init__(self, directory, user_id):
        if not user_id.strip():
            raise ValueError('A nonempty local user ID is required')
        key = os.environ.get('MINDWEAVE_KEY')
        if not key:
            raise ValueError('Set MINDWEAVE_KEY to a Fernet key before opting into persistence')
        self.cipher = Fernet(key.encode())
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / (hashlib.sha256(user_id.encode()).hexdigest() + '.enc')

    def load(self):
        return json.loads(self.cipher.decrypt(self.path.read_bytes())) if self.path.exists() else {'profile': {}, 'memories': {}, 'observations': []}

    def save(self, state):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_bytes(self.cipher.encrypt(json.dumps(state).encode()))
        temporary.replace(self.path)

    def delete(self):
        self.path.unlink(missing_ok=True)
