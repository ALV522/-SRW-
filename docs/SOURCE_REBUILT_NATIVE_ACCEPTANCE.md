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

## 首次使用：真正启动 Windows WPF/WebView2 并核验清理

新增 `scripts/accept_rebuilt_native_gui.py`。要求 Windows 10/11 的**交互式桌面会话**（不能以无桌面、无 WebView2 的 CI 后台任务冒充 GUI）。严格静态验证包后，在操作系统临时目录自动生成**全新且独立**的合成 SRW 数据工作区，启动包中的真正 `SmartRecruitmentWorkbench.exe`。操作者看到工作台后，用窗口右上角 **X 正常关闭**，测试器读取完整生命周期、进程退出与 `app.lock` 删除结果；默认 180 秒内完成。

```powershell
# 在含 scripts/accept_rebuilt_native_gui.py 的新版工具包/源码目录下：
py -3.12 .\scripts\accept_rebuilt_native_gui.py `
    --root 'D:\SRW\candidate-c8431ca7-clean' `
    --cycles 2 `
    --timeout 240 `
    --evidence 'D:\SRW\c8431ca7-wpf-two-cycles-new.json'
```

`--cycles 2` 会依次打开两次 WPF，需要你每次都在确认界面显示后正常关闭窗口。第二轮使用同一个**临时**工作区以验证重启、锁释放；脚本只接受本轮日志新增的事件，不会拿第一次结果冒充第二次成功。测试期间不会导入真实简历或 Provider Key，测试结束自动清理临时数据。仅保留脱敏事件名称、来源 SHA、成功/失败状态于新 JSON 报告。

**成功声明的边界**：这项烟测只能证明被测 SHA 的 WPF 窗口加载、Core Ready、WebView2 `frontend_loaded`、正常退出和锁释放，**不代表**完整业务、OCR/ASR、AI 或长期稳定性通过。如超时退出，进程会被清理但该轮明确标为 BLOCKED，不能声称优雅退出。已有的 `c8431ca7` 截图依旧是真实历史证据，但不是本脚本的新验收结果。

## #42：最终日志判定不得忽略失败

GUI 运行中的提示轮询可以等待尚未写完的 JSONL；进程退出后的最终判定必须严格解析本轮日志，要求同一非空 Host session，拒绝损坏的 JSON/UTF-8、缺少身份、跨会话拼接、强制终止、启动重试、关闭请求失败、后端异常和 HTTP 5xx。旧原文日志及新 `backend_http` / `backend_exception` 脱敏格式都须识别。只返回固定错误类别，不输出原始日志内容或会话 ID。

`convergence_tests/test_gui_evidence_fail_closed.py` 用合成 JSONL 验证上述拒绝行为与正常日志兼容性；这是验收器回归，**不是 Windows GUI 实机 PASS**。实际 WPF 工件、完整招聘、备份恢复与双端验收仍须分别执行。
