"""Keep test scratch files away from shared Windows temp directories."""
from pathlib import Path
from uuid import uuid4


def pytest_configure(config):
    if config.option.basetemp is None:
        root = Path(__file__).resolve().parent / '.test-runs'
        root.mkdir(exist_ok=True)
        # Pytest clears an explicit basetemp. Give each invocation a fresh,
        # nonexistent child so it never clears another user's/run's files.
        config.option.basetemp = str(root / f'run-{uuid4().hex}')
