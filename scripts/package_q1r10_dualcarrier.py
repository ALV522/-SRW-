"""Build a repeatable SRW Q1R10 pilot ZIP from a separately retained Native ZIP.

Only release *after* ownership/licence and real-Windows acceptance are checked.
This script never uploads any bytes; it changes no real user workspaces.
"""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_STORED, ZIP_DEFLATED

NATIVE_NAME = 'SRW_C11_NATIVE_1d273b67_UNVERIFIED_GUI.zip'
NATIVE_SIZE = 102272222
NATIVE_SHA = '708b6deddaab5bda7a1d13c93a740e6aed3d4e6dfa3eebe1637f99fdb661cb1e'
REQUIRED = ('VERSION', 'runtime/python.exe', 'scripts/start_local_web.py',
            'frontend/dist/index.html', 'windows-host/SmartRecruitmentWorkbench.exe') + tuple(
                f'knowledge/active/{name}/knowledge.db' for name in
                ('taxonomy', 'job_info', 'competency', 'market_reference', 'reference'))
STAMP = (2026, 11, 13, 0, 0, 0)

INSTALL_PS = r'''$ErrorActionPreference = 'Stop'
$InputZip = Join-Path $PSScriptRoot 'SRW_C11_NATIVE_1d273b67_UNVERIFIED_GUI.zip'
$OutputDir = Join-Path $PSScriptRoot 'SRW_APP'
$Expected = '708b6deddaab5bda7a1d13c93a740e6aed3d4e6dfa3eebe1637f99fdb661cb1e'
if (-not (Test-Path -LiteralPath $InputZip -PathType Leaf)) { throw 'Original Q1R10 ZIP is missing.' }
$Hash = (Get-FileHash -LiteralPath $InputZip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Hash -ne $Expected) { throw 'Q1R10 SHA mismatch. Refusing to install.' }
$MustHave = @('VERSION','runtime\python.exe','scripts\start_local_web.py',
  'frontend\dist\index.html','windows-host\SmartRecruitmentWorkbench.exe',
  'knowledge\active\taxonomy\knowledge.db','knowledge\active\job_info\knowledge.db',
  'knowledge\active\competency\knowledge.db',
  'knowledge\active\market_reference\knowledge.db','knowledge\active\reference\knowledge.db')
if (Test-Path -LiteralPath $OutputDir) {
  foreach ($Item in $MustHave) {
    if (-not (Test-Path -LiteralPath (Join-Path $OutputDir $Item) -PathType Leaf)) {
      throw "Existing SRW_APP incomplete ($Item). No overwrite permitted."
    }
  }
  Write-Host '[SRW] Existing app files preserved; no overwrite performed.'
} else {
  $Stage = Join-Path $PSScriptRoot ('SRW_INSTALL_STAGING_' + [guid]::NewGuid().ToString('N'))
  try {
    Expand-Archive -LiteralPath $InputZip -DestinationPath $Stage -ErrorAction Stop
    foreach ($Item in $MustHave) {
      if (-not (Test-Path -LiteralPath (Join-Path $Stage $Item) -PathType Leaf)) {
        throw "Extraction incomplete: $Item"
      }
    }
    $Version = (Get-Content -LiteralPath (Join-Path $Stage 'VERSION') -Raw -Encoding UTF8).Trim()
    if ($Version -ne '1.0.0-alpha10-convergence11') { throw "Unexpected version: $Version" }
    if (Test-Path -LiteralPath $OutputDir) { throw 'SRW_APP appeared during extraction; stopped.' }
    Move-Item -LiteralPath $Stage -Destination $OutputDir -ErrorAction Stop
    Write-Host '[SRW] Verified original Native ZIP installed into SRW_APP.'
  } catch { Write-Host '[SRW] Failed safely; original ZIP and user data not overwritten.'; throw }
}
Write-Host '[SRW] Ready: 02_START_SRW_EXE.cmd or 03_START_SRW_WEB.cmd.'
'''
INSTALL_CMD = r'''@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL-SRW.ps1"
if errorlevel 1 (
  echo [SRW] INSTALL FAILED. See the error above.
  pause
  exit /b 1
)
echo [SRW] Install complete.
pause
exit /b 0
'''
README = '''# SRW 双载体 Q1R10 本地试用版

此包为 **EARLY PILOT / GitHub Pre-release**，不是正式稳定版、RC 或 GA。

1. 在 Windows 10/11 将本 ZIP 完整解压到新目录。
2. 双击 `01_INSTALL_SRW.cmd`，它会先核验原始 Q1R10 ZIP SHA-256，再安装到 `SRW_APP`；不覆盖已安装程序或用户工作区。
3. 双击 `02_START_SRW_EXE.cmd`，使用 WPF/WebView2 桌面版；需要 .NET 10 Desktop Runtime 和 Edge WebView2 Runtime。
4. **关闭 EXE**，再双击 `03_START_SRW_WEB.cmd`，浏览器访问 `http://127.0.0.1:8765/v1`，在本机终端读取 60 秒一次性配对码完成配对。
5. Web 使用完毕，请在终端按 **Ctrl+C** 正常停止服务，然后才能再打开 EXE。

两者使用同一私有本机 SQLite `%LOCALAPPDATA%\\SRW\\DualCarrierV0\\data`，
**只允许串行切换**，不支持两个独立 Core 同时写入；不要删除 `app.lock`。
仅使用合成数据试用，不得上传生产简历、数据库、密钥或原始日志。

内置 Native ZIP SHA-256: `708b6deddaab5bda7a1d13c93a740e6aed3d4e6dfa3eebe1637f99fdb661cb1e`
Native Git SHA: `1d273b67bd0f571bd3c2e691e80a541c50e16f09`
启动脚本来自 [PR #259](https://github.com/ALV522/-SRW-/pull/259)。

B/C 在真实 Windows 使用本地修正后的启动器证明 EXE→Web→EXE 同库业务流程及互斥 PASS；
本 ZIP 这一**准确工件**仍应单独验收。#230/#43/#124/#130/#159 未关闭；不是生产发行授权。
公开上传前仍须确认第三方 Runtime/Knowledge 的再分发许可，不以本脚本替代来源审计。
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def add(z, name, data, *, compression=ZIP_DEFLATED):
    info = ZipInfo(name, STAMP)
    info.compress_type = compression
    info.external_attr = 0o644 << 16
    z.writestr(info, data, compress_type=compression, compresslevel=6)


def build(root, native_zip, output):
    root, native_zip, output = map(lambda p: Path(p).expanduser().resolve(), (root, native_zip, output))
    if output.exists() or output == native_zip or output.is_relative_to(root):
        raise ValueError('Output must be a new file outside source tree; do not overwrite an existing archive.')
    if native_zip.stat().st_size != NATIVE_SIZE or digest(native_zip.read_bytes()) != NATIVE_SHA:
        raise ValueError('Pinned original Native size/SHA mismatch; refusing to package.')
    with ZipFile(native_zip) as z:
        if len(z.namelist()) != 2812 or z.testzip() is not None:
            raise ValueError('Native inventory/ZIP CRC mismatch.')
        if any(f not in z.namelist() for f in REQUIRED):
            raise ValueError('Native essential files missing.')
        if z.read('VERSION').decode('utf-8').strip() != '1.0.0-alpha10-convergence11':
            raise ValueError('Native version mismatch.')
    exe = (root / 'START-SRW-EXE.cmd').read_text(encoding='utf-8')
    web = (root / 'START-SRW-WEB.cmd').read_text(encoding='utf-8')
    if '--application-root "%APPROOT_ARG%"' not in exe or '--application-root "%APPROOT%"' in exe:
        raise ValueError('EXE P1 path quoting fix is absent.')
    for script in (exe, web):
        if 'set "APPROOT=%~dp0"' not in script:
            raise ValueError('Unexpected launcher root identity.')
    exe = exe.replace('set "APPROOT=%~dp0"', 'set "APPROOT=%~dp0SRW_APP\\"', 1)
    web = web.replace('set "APPROOT=%~dp0"', 'set "APPROOT=%~dp0SRW_APP\\"', 1)
    files = {'01_INSTALL_SRW.cmd': INSTALL_CMD.encode('ascii'),
             'INSTALL-SRW.ps1': INSTALL_PS.encode('utf-8'),
             '02_START_SRW_EXE.cmd': exe.encode('ascii'),
             '03_START_SRW_WEB.cmd': web.encode('ascii'),
             'README_使用说明.md': README.encode('utf-8')}
    meta = {'status': 'EARLY_PILOT_NOT_GA', 'inner_native_sha256': NATIVE_SHA,
            'native_source_sha': '1d273b67bd0f571bd3c2e691e80a541c50e16f09',
            'files': {n: digest(b) for n, b in files.items()}}
    files['PACKAGE_INFO.json'] = (json.dumps(meta, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    with ZipFile(output, 'w', allowZip64=True) as z:
        for name, data in files.items():
            add(z, name, data)
        add(z, NATIVE_NAME, native_zip.read_bytes(), compression=ZIP_STORED)
    with ZipFile(output) as z:
        if z.testzip() is not None or digest(z.read(NATIVE_NAME)) != NATIVE_SHA:
            raise ValueError('Completed release ZIP failed verification.')
        for name, data in files.items():
            if z.read(name) != data:
                raise ValueError('Completed release ZIP member mismatch: ' + name)
    h = digest(output.read_bytes())
    (output.parent / (output.name + '.sha256')).write_text(h + '  ' + output.name + '\n', encoding='ascii')
    return h


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path, help='source checkout containing reviewed pilot launchers')
    parser.add_argument('--native-zip', required=True, type=Path, help='exact pinned Q1R10 original ZIP')
    parser.add_argument('--out', required=True, type=Path, help='new full release ZIP path outside checkout')
    args = parser.parse_args()
    print('SHA-256 ' + build(args.root, args.native_zip, args.out))
