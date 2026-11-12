"""Release workflow regressions: title, bilingual notes, conflicting versions, publish gate.

Background (1.20.0): the workflow published the title "ECU Studio AI 1.20.0" (without "v") and only the German
CHANGELOG section; both were corrected by hand afterwards. These tests keep that from happening again.
"""
import json
from pathlib import Path

import pytest

from ecu_studio.core import updates
from ecu_studio.tools.release_notes import (absolute_links, bilingual_sections, build_body, check_package, main,
                                            release_title)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / '.github' / 'workflows' / 'release.yml').read_text(encoding='utf-8')

CHANGELOG = '## Unveröffentlicht\n- offen\n\n## 2.0.0 (01.12.2026)\n\n- Neu: [Doku](docs/X.md)\n\n## 1.9.0\n- alt\n'
DOC = ('# ECU Studio AI 2.0.0 – Release Notes\n\nKopf\n\n---\n\n## Deutsch\n\nText\n\n### Neu\n- A\n\n'
       '### Bekannte Einschränkungen\n- B\n\n---\n\n## English\n\nText\n\n### New\n- A, see [Notes](CHECKSUMMEN.md#x)\n\n'
       '### Known limitations\n- B\n')


def test_release_title_is_always_ecu_studio_ai_v_version():
    assert release_title('v2.0.0', '2.0.0') == 'ECU Studio AI v2.0.0'
    for tag, version in (('2.0.0', '2.0.0'), ('v2.0.0-rc1', '2.0.0'), ('v2.0.1', '2.0.0')):
        with pytest.raises(ValueError):
            release_title(tag, version)


def test_workflow_publishes_the_generated_title_and_verifies_it():
    assert '--title "$(cat dist/release-title.txt)"' in WORKFLOW
    assert 'test "$(cat release-title.txt)" = "ECU Studio AI $TAG"' in WORKFLOW
    assert '--json name --jq .name)" = "ECU Studio AI $TAG"' in WORKFLOW
    # The wrong title of 1.20.0 must not come back.
    assert '--title "ECU Studio AI $version"' not in WORKFLOW


def test_body_has_german_notes_first_then_english_with_absolute_links():
    body = build_body(CHANGELOG, DOC, 'v2.0.0', '2.0.0')
    german, rest = body.split('\n---\n', 1)
    assert german.strip() == '- Neu: [Doku](https://github.com/PCTestAdmin/ECU-Studio-AI/blob/v2.0.0/docs/X.md)'
    assert '\n## English\n' in rest and '### Known limitations' in rest
    assert '](https://github.com/PCTestAdmin/ECU-Studio-AI/blob/v2.0.0/docs/CHECKSUMMEN.md#x)' in rest
    assert 'ECU-Studio-AI-2.0.0-setup.exe' in rest and '<version>' not in body
    assert 'Installation:' in rest and 'unzip' in rest                       # German and English install hints
    # The in-app update dialog shows only the German notes, without footer or English part.
    payload = {'tag_name': 'v2.0.0', 'body': body, 'html_url': '', 'assets': [
        {'name': 'ECU-Studio-AI-2.0.0-windows-x64.zip', 'size': 1,
         'browser_download_url': 'https://github.com/PCTestAdmin/ECU-Studio-AI/releases/download/v2.0.0/ECU-Studio-AI-2.0.0-windows-x64.zip'},
        {'name': 'ECU-Studio-AI-2.0.0-windows-x64.zip.sha256', 'size': 1,
         'browser_download_url': 'https://github.com/PCTestAdmin/ECU-Studio-AI/releases/download/v2.0.0/ECU-Studio-AI-2.0.0-windows-x64.zip.sha256'}]}
    assert updates.parse_release(payload).notes == german.strip()


@pytest.mark.parametrize('doc, message', [
    (DOC.split('## English')[0], 'English'),                                             # translation missing
    (DOC.replace('### Known limitations\n- B\n', ''), 'unvollständig'),                  # translation incomplete
    (DOC.replace('## English\n\nText\n\n### New\n- A, see [Notes](CHECKSUMMEN.md#x)\n\n### Known limitations\n- B\n',
                 '## English\n\n'), 'English'),                                         # empty English section
    (DOC.replace('## Deutsch', '## German'), 'Deutsch'),
    (DOC.replace('2.0.0 – Release', '1.9.0 – Release'), 'Version 1.9.0'),                # notes of another version
    (DOC.replace('# ECU Studio AI 2.0.0 – Release Notes', '# Release Notes'), 'erste Zeile'),
])
def test_missing_or_incomplete_translation_and_wrong_version_fail(doc, message):
    with pytest.raises(ValueError, match=message):
        bilingual_sections(doc, '2.0.0')


def test_conflicting_versions_fail(tmp_path):
    with pytest.raises(ValueError, match='CHANGELOG'):
        build_body(CHANGELOG.replace('## 2.0.0', '## 2.0.1'), DOC, 'v2.0.0', '2.0.0')
    with pytest.raises(ValueError, match='passt nicht'):
        build_body(CHANGELOG, DOC, 'v2.0.0', '2.0.1')
    package = tmp_path / 'ECU-Studio-AI'
    package.mkdir()
    (package / 'VERSION.txt').write_text('2.0.0\n', encoding='ascii')
    (package / 'RUNTIME_INVENTORY.json').write_text(json.dumps({'format': 1, 'version': '2.0.0', 'files': []}))
    check_package(package, '2.0.0')
    for version_txt, inventory in (('1.9.0', '2.0.0'), ('2.0.0', '1.9.0')):
        (package / 'VERSION.txt').write_text(version_txt + '\n', encoding='ascii')
        (package / 'RUNTIME_INVENTORY.json').write_text(json.dumps({'format': 1, 'version': inventory, 'files': []}))
        with pytest.raises(ValueError, match='erwartet 2.0.0'):
            check_package(package, '2.0.0')
    with pytest.raises(ValueError, match='nicht lesbar'):
        check_package(tmp_path / 'fehlt', '2.0.0')


def test_command_fails_without_bilingual_notes_and_writes_title(tmp_path, monkeypatch):
    import ecu_studio.tools.release_notes as tool
    monkeypatch.setattr(tool, 'check_tag', lambda tag, version='2.0.0': '2.0.0')
    monkeypatch.setattr(tool, 'release_title', lambda tag, version='2.0.0': f'ECU Studio AI {tag}')
    changelog = tmp_path / 'CHANGELOG.md'
    changelog.write_text(CHANGELOG, encoding='utf-8')
    docs = tmp_path / 'docs'
    docs.mkdir()
    out, title = tmp_path / 'notes.md', tmp_path / 'title.txt'
    args = ['v2.0.0', '--out', str(out), '--title-out', str(title), '--changelog', str(changelog), '--docs', str(docs)]
    assert main(args) == 1 and not out.exists()                                  # RELEASE_NOTES_2.0.0.md missing
    (docs / 'RELEASE_NOTES_2.0.0.md').write_text(DOC.split('## English')[0], encoding='utf-8')
    assert main(args) == 1 and not out.exists()                                  # English part missing
    (docs / 'RELEASE_NOTES_2.0.0.md').write_text(DOC, encoding='utf-8')
    assert main(args) == 0
    assert title.read_text(encoding='utf-8') == 'ECU Studio AI v2.0.0\n' and '## English' in out.read_text(encoding='utf-8')
    assert b'\r\n' not in out.read_bytes()


def test_published_release_notes_of_1_20_0_build_the_published_body():
    """The real 1.20.0 notes produce the bilingual body that was published by hand (no relative links left)."""
    changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    doc = (ROOT / 'docs' / 'RELEASE_NOTES_1.20.0.md').read_text(encoding='utf-8')
    body = build_body(changelog, doc, 'v1.20.0', '1.20.0')
    assert body.count('\n## English\n') == 1 and '**Fünf Status:**' in body and 'Central checksum and integrity system' in body
    assert absolute_links('[a](b.md) [c](https://x) [d](#e)', 'v1', 'docs/') == (
        '[a](https://github.com/PCTestAdmin/ECU-Studio-AI/blob/v1/docs/b.md) [c](https://x) [d](#e)')


def test_workflow_gates():
    # Only a pushed tag publishes; dry-run branches build and test but never publish.
    assert "tags: ['v*.*.*']" in WORKFLOW and "branches: ['release-dry-run/**']" in WORKFLOW
    assert "if: github.ref_type == 'tag'" in WORKFLOW
    # Firmware guard, model block, version checks, installer test, checksums and provenance before/after publishing.
    assert 'firmware_guard.py tree HEAD' in WORKFLOW
    assert '-m ecu_studio.tools.withdrawn' in WORKFLOW
    assert '--package dist/ECU-Studio-AI' in WORKFLOW and 'VersionInfo.ProductVersion' in WORKFLOW
    assert "release-test-user-file.txt" in WORKFLOW and 'DisplayVersion -ne $version' in WORKFLOW
    assert 'sha256sum "$f"' in WORKFLOW and 'actions/attest-build-provenance' in WORKFLOW
    assert 'gh attestation verify' in WORKFLOW
    assert WORKFLOW.index('needs: [build, update-test]') < WORKFLOW.index('gh release create')
