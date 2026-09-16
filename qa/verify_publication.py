#!/usr/bin/env python3
"""Check the exact public snapshot, local links, media and tracked file list."""
import hashlib
import json
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids, self.images = [], set(), []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids.add(attrs['id'])
        for key in ('href', 'src'):
            if attrs.get(key):
                self.links.append(attrs[key])
        if tag == 'img':
            self.images.append(attrs.get('src'))


def verify():
    manifest = json.loads((SITE / 'publication-manifest.json').read_text())
    actual = {str(p.relative_to(SITE)) for p in SITE.rglob('*')
              if p.is_file() and p.name != 'publication-manifest.json'}
    assert actual == set(manifest['files']), 'Unreviewed or missing site files'
    assert manifest['rawCaptureIncluded'] is False
    assert manifest['appSourceRevision'] == 'HOVER_INTENT_V2_4'
    assert manifest['combinedReportImages'] == 4
    assert manifest['combinedReportSourceSha256'] == [
        '1c2eff5549ea4bafb76b2d7e683e31ef5db07187161ffe2bda50f25859940b89',
        '780e62eac61e35d1412bb59e0532ffe0561365fa7238459e4785470ac12c7f12',
        '270a784611dca91aaa34d783ccdfcb916b249f9307a49d4d03cd66e6984518ba']
    for name, item in manifest['files'].items():
        path = SITE / name
        assert path.is_file() and not path.is_symlink(), name
        assert path.stat().st_size == item['bytes'] and digest(path) == item['sha256'], name
        assert path.suffix.lower() not in ('.csv', '.ipa', '.mobileprovision', '.p12', '.bin'), name
        assert path.name not in ('replay-data.json', 'v2_trajectories.json', 'motion_metrics.csv'), name
        assert path.stat().st_size < 50_000_000, 'Unexpected large file: ' + name
        if path.suffix in ('.html', '.md', '.json', '.js'):
            text = path.read_text()
            assert '/Users/' not in text, 'Local path in ' + name
            assert not re.search(r'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]+', text), name
            assert not re.search(r'\b[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\b', text), 'Unredacted ID in ' + name
    parsed = {}
    for path in SITE.rglob('*.html'):
        parser = Links()
        parser.feed(path.read_text())
        parsed[path.resolve()] = parser
    count = 0
    for path, parser in parsed.items():
        for link in parser.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            assert target.is_relative_to(SITE.resolve()), (path, link)
            if target.is_dir():
                target = target / 'index.html'
            assert target.is_file(), 'Broken public link: ' + str((path.name, link))
            if url.fragment and target in parsed:
                assert url.fragment in parsed[target].ids, 'Missing anchor: ' + link
            count += 1
    report = SITE / 'report/study-report.html'
    combined = SITE / 'report/combined.html'
    assert all('section-' + str(i) in parsed[report.resolve()].ids for i in range(1, 13))
    assert len(parsed[report.resolve()].images) == 17
    assert len(parsed[combined.resolve()].images) == 4
    assert all(section in parsed[combined.resolve()].ids for section in ('motion', 'home', 'gaze'))
    assert 'report/combined.html' in parsed[(SITE/'index.html').resolve()].links
    assert 'V2.4' in (SITE/'install.html').read_text()
    snapshot = json.loads((SITE / 'report/study-report.json').read_text())
    assert snapshot['participants'] == 1 and snapshot['hand'] == 'RIGHT'
    assert snapshot['measuredProtocol'] == 'HOVER_INTENT_V2_1'
    assert snapshot['appRevision'] == 'HOVER_INTENT_V2_3'
    def no_raw(value):
        if isinstance(value, dict):
            assert not set(value).intersection({'raw', 'samples', 'segments', 'events', 'pointsRaw', 'trialID', 'deviceID'})
            for item in value.values():
                no_raw(item)
        elif isinstance(value, list):
            for item in value:
                no_raw(item)
    no_raw(snapshot)
    dataset = re.search(r'<script id="dataset" type="application/json">(.*?)</script>',
                        (SITE / 'replay/replay-v2.html').read_text(), re.S)
    assert dataset and json.loads(dataset[1])['trials'] == []
    for root in (ROOT / 'src/App/StudyMedia', SITE / 'replay/Resources'):
        media = json.loads((root / 'media-manifest.json').read_text())
        assert media['license'] == 'CC BY 3.0' and len(media['clips']) == 6
        for clip in media['clips']:
            assert digest(root / (clip['id'] + '.mp4')) == clip['sha256']
    for root in (ROOT / 'qa/vendor', SITE / 'replay/vendor'):
        assert (root / 'THREE-LICENSE.txt').is_file()
        for name in ('three.module.js', 'three.core.js', 'OrbitControls.js'):
            assert (root / name).is_file()
    tracked = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True).stdout.decode().split('\0')
    tracked = [name for name in tracked if name]
    assert tracked, 'Stage or commit the explicit publishing file list first'
    for name in tracked:
        assert not name.startswith(('data/', 'analysis/', 'backups/', '.tmp/', 'qa/device-')), name
        assert not any(part in name.split('/') for part in ('__pycache__', '.build', 'xcuserdata')), name
        assert Path(name).suffix.lower() not in ('.csv', '.ipa', '.mobileprovision', '.p12', '.bin', '.log'), name
        path = ROOT / name
        assert path.stat().st_size < 50_000_000, name
        if path.suffix.lower() in ('.swift', '.py', '.js', '.md', '.json', '.yml', '.pbxproj', '.plist'):
            text = path.read_text()
            assert '/Users/' not in text or name in ('qa/build_public_site.py', 'qa/verify_publication.py'), name
            assert not re.search(r'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]+', text), name
            assert not re.search(r'DEVELOPMENT_TEAM\s*=\s*"?[A-Z0-9]{10}', text), name
    result = {'status': 'PASS', 'trackedFiles': len(tracked), 'siteFiles': len(actual),
              'localLinksChecked': count, 'reportChapters': 12, 'reportImages': 17,
              'combinedImages': 4, 'appSourceRevision': 'HOVER_INTENT_V2_4',
              'rawCaptureIncluded': False, 'replayStartsEmpty': True}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    verify()
