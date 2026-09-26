"""Explicit, read-only release checks. Never download or execute update binaries."""
import json
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from killcutter import __version__

RELEASES = 'https://github.com/Ritvik2706/killdetectionScript/releases'
API = 'https://api.github.com/repos/Ritvik2706/killdetectionScript/releases/latest'


def version_tuple(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', value)
    if not match:
        raise ValueError('Release version must be a stable major.minor.patch version.')
    return tuple(int(part) for part in match.groups())


def check():
    request = Request(API, headers={'Accept': 'application/vnd.github+json',
                                   'User-Agent': f'KillcutterStudio/{__version__}'})
    try:
        with urlopen(request, timeout=10) as response:
            payload = response.read(1_000_001)
            if len(payload) > 1_000_000:
                raise ValueError('Release response exceeds the size limit.')
            data = json.loads(payload)
            if not isinstance(data, dict):
                raise ValueError('Invalid release response.')
    except HTTPError as exc:
        if exc.code == 404:
            return 'No public release is available yet.', RELEASES
        raise
    version = data.get('tag_name', '')
    newer = version_tuple(version) > version_tuple(__version__)
    return (f'Version {version} is available. You have {__version__}.' if newer
            else f'You are up to date ({__version__}).'), RELEASES
