"""Generate files only. Installing/loading launch agents is an explicit operator action."""
import os
from pathlib import Path
import plistlib

ROOT = Path(__file__).resolve().parents[1]


def generate():
    folder = ROOT / 'deploy/generated'
    folder.mkdir(exist_ok=True, parents=True)
    jobs = {
        'com.analog.store': {
            'ProgramArguments': [str(ROOT / '.venv/bin/python'), '-m', 'backend.run'],
            'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 10,
        },
        'com.analog.store.backup': {
            'ProgramArguments': [str(ROOT / '.venv/bin/python'), str(ROOT / 'scripts/backup.py')],
            'StartCalendarInterval': {'Hour': 4, 'Minute': 15}, 'RunAtLoad': False,
        },
    }
    for label, options in jobs.items():
        obj = {'Label': label, 'WorkingDirectory': str(ROOT), 'Umask': 0o077,
               'EnvironmentVariables': {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin'},
               'StandardOutPath': str(ROOT / 'var/log' / (label + '.out.log')),
               'StandardErrorPath': str(ROOT / 'var/log' / (label + '.err.log')), **options}
        path = folder / (label + '.plist')
        path.write_bytes(plistlib.dumps(obj))
        os.chmod(path, 0o600)
        print(path)


if __name__ == '__main__':
    generate()
