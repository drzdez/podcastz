import keyring
import pytest
from keyring.backend import KeyringBackend


class FakeVault(KeyringBackend):
    """In-memory credential store: tests must never read or write the real OS vault."""
    priority = 1

    def __init__(self):
        super().__init__()
        self.data = {}

    def get_password(self, service, username):
        return self.data.get((service, username))

    def set_password(self, service, username, password):
        self.data[(service, username)] = password

    def delete_password(self, service, username):
        self.data.pop((service, username), None)


@pytest.fixture(autouse=True)
def fake_vault(monkeypatch):
    previous = keyring.get_keyring()
    vault = FakeVault()
    keyring.set_keyring(vault)
    for name in ('OPENAI_API_KEY', 'ELEVENLABS_API_KEY', 'PODCASTZ_OPENAI_API_KEY', 'PODCASTZ_ELEVENLABS_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    yield vault
    keyring.set_keyring(previous)
