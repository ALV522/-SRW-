# C11 源码重建 Native 候选包：正式静态验收与隔离后端实测

> 适用对象：`scripts/rebuild_native_from_prepared.py` 产出的 `source_rebuild_not_legacy_carrier`，例如已在 Windows 真实启动的 `c8431ca7` Native ZIP。**不适用旧 v0.8.x 或历史 Prepared 身份**，后者仍须使用原验证器。

## 解决的交付问题

旧 `scripts/verify_prepared_native.py` 只接受 d8d032d 的 `PREPARED` 原始工件元数据（如 `prepared_status`、`embedded_python_windows_smoke_passed=false`）。新源码重建包已使用 `srw.native-source-built-host-provenance.v1`，`host_origin=source_rebuild_not_legacy_carrier`。因此不能以旧验证器返回“prepared payload provenance mismatch”来推断新包损坏。

新版 `scripts/verify_rebuilt_native.py` **严格限定**源码重建来源：读 `SOURCE_MANIFEST.sha256`、`PRODUCTION_RUNTIME.sha256`、`PRODUCTION_KNOWLEDGE.sha256`、真实 WPF EXE SHA、同 SHA Host build truth，以及全部 ZIP 成员；严格检查五库 SQLite Integrity 和 C11 依赖版本锁。明确保留 `windows_gui_accepted=false`，不会擅自提高发布等级。

## 使用方式

必须使用**包含此脚本的最新版独立工具包/源码**；旧 `c8431ca7` ZIP 本身是在此功能开发前打成的，不包含新验证脚本。

在装配好的新版工具包或有 `scripts/verify_rebuilt_native.py` 的新 Native 候选包根目录执行；先在新路径解压原始 Native ZIP，不要覆盖已经完成实机操作的旧目录：

```powershell
$app = 'D:\SRW\candidate-c8431ca7-clean'
$zip = 'D:\SRW\SRW_C11_c8431ca7_UNVERIFIED_GUI.zip'
$expected = '560685a3ce54426fb815dd88465b781378d5096d87a37e94a82e296c6752ec69'
$evidence = 'D:\SRW\audit-c8431ca7-static-new.json'

# 确保 $app 是从 $zip 新解压的原样目录；
# 它应包含 runtime/、knowledge/active/、windows-host/。
py -3.12 .\scripts\verify_rebuilt_native.py `
    --root $app `
    --zip $zip `
    --expected-zip-sha256 $expected `
    --evidence $evidence
```

**正式 Windows 嵌入式 Python / Core 后端烟测**：在 `--evidence` 处使用**新的报告文件名**，加上 `--backend-smoke`：

```powershell
py -3.12 .\scripts\verify_rebuilt_native.py `
    --root $app `
    --zip $zip `
    --expected-zip-sha256 $expected `
    --backend-smoke `
    --evidence 'D:\SRW\audit-c8431ca7-embedded-new.json'
```

该烟测从经验证的 Native `runtime/python.exe` 启动原生 C11 回环 Core，只使用短期、隔离的临时数据库，重新验证 Windows 后端运行时身份与实际导入来源；不打开用户已有的 SRW 工作区。**它不启动 WPF 窗口**，因此依旧不等于 GUI 或招聘业务实机验收。

## 独立真实工件静态试验

2026-10-19，开发时直接使用用户已上传的完整 `SRW_C11_c8431ca7_UNVERIFIED_GUI.zip`：

- 原始完整 ZIP SHA：`560685a3ce54426fb815dd88465b781378d5096d87a37e94a82e296c6752ec69`；
- Source：290 个条目，Runtime：2,332 个文件；
- Knowledge：5 个 DB，Host：15 个文件；
- 来源 SHA：`c8431ca7012070ff27fd88a219755ea4335cbd68`；
- 最终报告 `SOURCE_REBUILD_STATIC_PASS_GUI_NOT_YET_ACCEPTED`，全部静态成员与 CRC/SHA 审计通过；
- 未在本次 Linux 开发环境中运行 Windows `--backend-smoke` 或真正 WPF GUI；不能标为 GUI PASS。

新脚本是后续版本的一部分；历史用户 ZIP 本身保持不变。

## 故障边界

- 使用真实招聘数据库进行 Native 烟测：**禁止**；临时 Core/数据库会由脚本管理。
- `--expected-zip-sha256` 不接受未知来源临时重算的“新值”；应以独立记录的 ZIP SHA 为准。
- 含 `__pycache__`、私有文件、额外 DB 或被用户覆盖修改的程序目录：严格拒绝；请新解压原始 ZIP 再跑静态审计。
- 任何 SHA、Host 身份、Schema 或 Runtime 依赖不匹配：输出 `BLOCKED`，并返回非零退出码。
- 报告必须放在程序目录外，且不能覆盖已经存在的报告文件。

下一道验收：真实 WPF GUI 的 Source/Claim/Decision/Scorecard/Offer 纵向操作、备份恢复、后台任务稳定性、OCR/ASR/AI、重启/升级回滚，最后才能考虑 RC。
