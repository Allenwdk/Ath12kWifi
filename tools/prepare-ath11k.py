#!/usr/bin/env python3
"""Prepare the locked upstream ath11k core and WCN6750 AHB sources.

Protocol and hardware code is unchanged. Disabled trace points use the same
generated no-op declarations as the existing ath12k preparation. Build gaps
must be implemented in the shared compatibility layer or board callbacks.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    lock = json.loads((ROOT / 'tools/source-lock.json').read_text())['linux']
    linux = ROOT / 'deps/linux'
    revision = subprocess.check_output(['git', '-C', str(linux), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != lock['commit']:
        raise SystemExit('ath11k must use the same locked Linux revision as mac80211/cfg80211')
    source = linux / 'drivers/net/wireless/ath/ath11k'
    output = ROOT / 'out/ath11k-src'
    output.mkdir(parents=True, exist_ok=True)
    hashes = {}
    trace_names = set()
    for path in sorted(source.parent.glob('*.h')):
        shutil.copyfile(path, output.parent / path.name)
        hashes['../' + path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(source.iterdir()):
        if path.suffix not in ('.c', '.h'):
            continue
        data = path.read_bytes()
        hashes[path.name] = hashlib.sha256(data).hexdigest()
        trace_names.update(re.findall(r'\btrace_ath11k_[a-z_0-9]+', data.decode()))
        if path.name != 'trace.h':
            shutil.copyfile(path, output / path.name)
    (output / 'trace.h').write_text('/* CONFIG_ATH11K_TRACING is disabled. */\n' +
                                   '\n'.join(f'#define {name}(...) ' + ('0' if name.endswith('_enabled') else '((void)0)')
                                             for name in sorted(trace_names)) + '\n')
    makefile = (source / 'Makefile').read_text()
    core = makefile.split('ath11k-y +=', 1)[1].split('ath11k-$(', 1)[0]
    selected = [name + '.c' for name in re.findall(r'\b([a-z0-9_]+)\.o\b', core)] + ['ahb.c']
    (ROOT / 'out/ath11k-identity.json').write_text(json.dumps({
        'linux_revision': revision,
        'source_sha256': hashes,
        'sources': selected,
        'configuration': ['CONFIG_ATH11K', 'CONFIG_ATH11K_AHB', 'CONFIG_ATH11K_DEBUG'],
        'trace_disabled': True,
        'hardware_verified': False,
    }, indent=2) + '\n')
    print(f'ath11k: {len(selected)} original core/AHB sources at {revision}')


if __name__ == '__main__':
    main()
