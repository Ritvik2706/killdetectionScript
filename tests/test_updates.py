import json
from io import BytesIO
from urllib.error import HTTPError
import pytest
from killcutter.gui import updates


def test_update_check_only_reads_official_release(monkeypatch):
    requests = []
    def read(request, timeout):
        requests.append(request.full_url)
        assert timeout == 10
        return BytesIO(json.dumps({'tag_name': 'v99.0.0'}).encode())
    monkeypatch.setattr(updates, 'urlopen', read)
    message, url = updates.check()
    assert 'available' in message
    assert url == updates.RELEASES
    assert requests == [updates.API]


def test_missing_release_is_not_an_error(monkeypatch):
    def read(*args, **kwargs):
        raise HTTPError(updates.API, 404, 'not found', {}, None)
    monkeypatch.setattr(updates, 'urlopen', read)
    assert 'No public release' in updates.check()[0]


@pytest.mark.parametrize('version', ['v1.0.0-beta', '', 'latest', '1.2'])
def test_unrecognized_release_versions_are_rejected(version):
    with pytest.raises(ValueError):
        updates.version_tuple(version)
