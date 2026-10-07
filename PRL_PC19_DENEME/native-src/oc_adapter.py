"""Explicit, locally verified OC-tool boundary; no guessed GPU reset commands."""
import subprocess
from pathlib import Path
import os


class OCAdapter:
    def __init__(self, settings, root, validate_binary):
        self.settings = settings
        self.root = root
        self.validate_binary = validate_binary
        self.dirty = False

    def _run(self, action):
        if not self.settings['enabled']:
            return
        if self.settings['adapter_verified'] is not True:
            raise ValueError('OC adapter has not been verified on this GPU/driver')
        exe = Path(self.settings['exe'])
        if not exe.is_absolute():
            exe = self.root / exe
        exe = exe.resolve()
        self.validate_binary(exe, self.settings['exe_sha256'])
        args = self.settings[f'{action}_args']
        if not args:
            raise ValueError(f'OC {action} arguments are missing')
        # Tool must be a trusted native EXE. No shell, arbitrary batch, or auto OC.
        subprocess.run([str(exe), *args], check=True, capture_output=True,
            timeout=5, creationflags=0x08000000 if os.name == 'nt' else 0)

    def apply(self):
        # A failed command might already have partially changed GPU settings.
        self.dirty = self.settings['enabled']
        self._run('apply')

    def restore(self, force=False):
        if self.dirty or force:
            self._run('restore')
            self.dirty = False
