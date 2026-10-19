"""Create source/runtime ZIPs after successful QA, without overwriting archives."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def main():
    root=Path(__file__).resolve().parent
    history=root/'docs'/'history'
    qa=json.loads((history/'QA_REPORT_V114.json').read_text(encoding='utf-8'))
    if qa['final_tests']['failures'] or qa['final_tests']['errors'] or not qa['packaged_exe_gui']['passed']:
        raise RuntimeError('Successful final QA required')
    executable=root/qa['exe']['path']
    if hashlib.sha256(executable.read_bytes()).hexdigest()!=qa['exe']['sha256']:
        raise RuntimeError('EXE changed after QA')
    inventory=executable.parent/'RUNTIME_INVENTORY.json'
    if hashlib.sha256(inventory.read_bytes()).hexdigest()!=qa['exe']['runtime_inventory_sha256']:
        raise RuntimeError('Runtime inventory changed after QA')
    expected=json.loads(inventory.read_text(encoding='utf-8'))['files']
    expected_names={item['path'] for item in expected}|{'RUNTIME_INVENTORY.json'}
    actual_names={p.relative_to(executable.parent).as_posix() for p in executable.parent.rglob('*') if p.is_file()}
    if actual_names!=expected_names:raise RuntimeError('Unexpected or missing runtime files after QA')
    for item in expected:
        p=executable.parent/item['path']
        if hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:
            raise RuntimeError('Runtime changed after QA: '+item['path'])
    def check_private(path):
        private=qa.get('real_binary',{})
        if path.stat().st_size==private.get('size') and hashlib.sha256(path.read_bytes()).hexdigest()==private.get('sha256'):
            raise RuntimeError('Private regression firmware must never enter release archives')
    release=root/'release'
    release.mkdir(exist_ok=True)
    source=release/'ECU-Studio-AI-1.14-source.zip'
    windows=release/'ECU-Studio-AI-1.14-windows-x64.zip'
    if source.exists() or windows.exists():
        raise FileExistsError('Existing release archives are never overwritten')
    omitted={'.venv','.qa','qa-artifacts','build','dist','release','__pycache__','.pytest_cache','.git'}
    with ZipFile(source,'x',ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob('*')):
            relative=path.relative_to(root)
            if (not path.is_file() or any(part in omitted or part.endswith('.egg-info') for part in relative.parts)
                    or path.suffix in ('.pyc','.spec')):
                continue
            check_private(path)
            archive.write(path,'ECU-Studio-AI-1.14/'+relative.as_posix())
    docs=('README_V1_14.md','DETECTION_REPORT_V114.md','FEATURE_MATRIX_V114.md','REAL_MS43_AUDIT_V114.json','REAL_MS42_AUDIT_V114.json','TRAINING_REPORT_V113.json',
          'QA_REPORT_V114.json','ROMRAIDER_FORMAT_AUDIT_V113.json','README_V1_12.md','FEATURE_MATRIX_V112.md',
          'README_V1_11.md','FEATURE_MATRIX_V111.md','DELIVERY_REPORT_V111.md')
    with ZipFile(windows,'x',ZIP_DEFLATED) as archive:
        for path in sorted(executable.parent.rglob('*')):
            if path.is_file():
                check_private(path)
                archive.write(path,'ECU-Studio-AI-1.14/'+path.relative_to(executable.parent).as_posix())
        for name in docs:
            archive.write(history/name,'ECU-Studio-AI-1.14/'+name)
    result=[]
    for path in (source,windows):
        with ZipFile(path) as archive:
            failed=archive.testzip()
            if failed:
                raise RuntimeError('ZIP CRC failed: '+failed)
            count=len(archive.infolist())
        result.append({'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                       'bytes':path.stat().st_size,'entries':count,'zip_crc_verified':True})
    sums=release/'SHA256SUMS.json'
    previous=json.loads(sums.read_text(encoding='utf-8')) if sums.exists() else []
    sums.write_text(json.dumps(previous+result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
