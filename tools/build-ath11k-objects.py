#!/usr/bin/env python3
"""Compile original ath11k/AHB objects with the production target and shim.

This is a porting build, not a complete linked backend. Failures and missing
imports are retained in a report; a failed object never counts as built.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', default='arm64e-apple-ios27.0.0')
    parser.add_argument('--jobs', type=int, default=8)
    args = parser.parse_args()
    subprocess.run(['python3', str(ROOT / 'tools/prepare-ath11k.py')], check=True)
    identity = json.loads((ROOT / 'out/ath11k-identity.json').read_text())
    out = ROOT / 'out/ath11k-kernel-objects'
    out.mkdir(parents=True, exist_ok=True)
    clang = subprocess.check_output(['xcrun', '-f', 'clang'], text=True).strip()
    resource = subprocess.check_output([clang, '-print-resource-dir'], text=True).strip() + '/include'
    flags = ['-target', args.target, '-mkernel', '-O2', '-g0', '-ffreestanding', '-fno-builtin', '-fno-common',
             '-fno-strict-aliasing', '-fwrapv', '-fno-stack-protector', '-mgeneral-regs-only', '-std=gnu11',
             '-Wno-error', '-Wno-incompatible-pointer-types', '-w', '-ferror-limit=24', '-DCONFIG_ATH11K=1', '-DCONFIG_ATH11K_AHB=1',
             '-DCONFIG_ATH11K_DEBUG=1', '-DNW_PLATFORM_AHB=1', '-DCONFIG_CFG80211=1', '-DCONFIG_MAC80211=1',
             '-DCONFIG_MAC80211_STA_HASH_MAX_SIZE=0', '-DCONFIG_MAC80211_RC_DEFAULT=""',
             '-nostdinc', '-isystem', str(ROOT / 'shim/libc'), '-isystem', resource, '-include', 'lx_pci.h']
    for include in ['shim/include', 'include', 'out/pinned', 'out/ath11k-src', 'out', 'src']:
        flags.extend(['-I', str(ROOT / include)])

    def build(name):
        source, obj = ROOT / 'out/ath11k-src' / name, out / Path(name).with_suffix('.o')
        obj.unlink(missing_ok=True)
        command = [clang, *flags, '-c', str(source), '-o', str(obj)]
        result = subprocess.run(command, capture_output=True, text=True)
        (out / (name + '.log')).write_text(result.stdout + result.stderr)
        imports = []
        if result.returncode == 0:
            imports = subprocess.check_output(['llvm-nm', '-u', str(obj)], text=True).splitlines()
        return {'source': name, 'exit_code': result.returncode, 'object': str(obj) if result.returncode == 0 else None,
                'undefined': imports, 'log': str(out / (name + '.log')), 'command': command}

    with ThreadPoolExecutor(args.jobs) as workers:
        results = list(workers.map(build, identity['sources']))
    built = sum(r['exit_code'] == 0 for r in results)
    (out / 'build-report.json').write_text(json.dumps({'target': args.target, 'built': built,
        'total': len(results), 'linux_revision': identity['linux_revision'], 'results': results,
        'linked_backend': False, 'hardware_verified': False}, indent=2) + '\n')
    print(f'ath11k native objects: {built}/{len(results)}; see {out}/build-report.json')
    for result in results:
        if result['exit_code']:
            errors = [line for line in Path(result['log']).read_text().splitlines() if 'error:' in line]
            print(result['source'] + ': ' + ' | '.join(errors[:2]))
    raise SystemExit(0 if built == len(results) else 1)


if __name__ == '__main__':
    main()
