# Windows C11 首次实机反馈与可重复验收修复（2026-10-19）

## 已收到的真实验收事实

用户在 Windows PowerShell 中使用 `py -3.12` 运行 `scripts/verify_prepared_native.py`，检查已解压的历史候选 ZIP `SRW_C11_Windows_Native_PREPARED_UNVERIFIED_GUI_d8d032d.zip`。首次执行返回：

- `source_file_count=273`、`runtime_file_count=2332`、`knowledge_databases=5`、`host_members=15`、`pinned_dependencies=13`；
- `source_sha=d8d032de255c87839adbeedc5737124d7fbfc3cd`；
- **`EMBEDDED_PYTHON_AND_LOOPBACK_BACKEND_SMOKE_PASS`**（真实 Windows 嵌入式 Python 3.12.10、十三项依赖导入、本地 C11 后端就绪和 Host ABI 身份检查成功）；
- `status=WINDOWS_BACKEND_SMOKE_PASS_GUI_PENDING`、`gui_accepted=false`；
- 完整 JSON 证据已保存到本机 `D:\SRW\evidence\C11-Windows-smoke.json`，不是 GitHub Actions 生成的假验收。

这是**真实用户机器上的后端验收成功证据**，不等于 WPF/WebView2 前端已验收。

随后的重复执行返回 `BLOCKED: extracted Native candidate contains missing or unreviewed files`。在首次运行后，旧验证器用 `runtime/python.exe -I -c` 导入模块而**没有关闭 CPython 的磁盘字节码缓存写入**；产生未列入压缩包原始 SHA 清单的 `__pycache__/*.pyc` 是主要怀疑原因，**具体增加了什么文件仍应由新版诊断输出确认**，不应自动归类为无害，也不能以此取消完整文件审计。重复命令还错误地重用了已经存在的证据文件；首次 JSON 不应覆盖。

## 本轮代码修复

- `scripts/verify_prepared_native.py`：实际 import smoke 使用 `python.exe -I -B`；后端使用 `python.exe -B`。对不一致文件集合输出 `unexpected_count`、`missing_count` 和有限的路径样本，原来的未知文件拦截保持不变。已有证据文件在执行前直接拒绝覆盖。
- `desktop/SRW.Desktop/Hosting/BackendProcess.cs`：WPF Host 启动嵌入式 Python 时传入 `-B`，并设置 `PYTHONDONTWRITEBYTECODE=1`，以确保新编译 Host 默认不更改程序根目录。
- `convergence_tests/test_prepared_native_smoke.py`：新增验证未登记 bytecode 不得放行、命令行禁写入字节码和既有证据文件不可重写的回归案例。

**重要：这些源码修复不会直接改写原来 SHA 为 d8d032d 的 101.6 MB ZIP。** GitHub 的最新验收脚本可以用来检查原包，但修复后的 Windows Host 只有重编译成另一 SHA 的 Host 候选时才能成为正式工件的一部分。旧 Host 可通过从 PowerShell 设置 `PYTHONDONTWRITEBYTECODE=1` 来防止其后端继续生成缓存。

## 用户现在需要执行的下一步

1. 保留 `D:\SRW\evidence\C11-Windows-smoke.json`；这个首次成功的 JSON 已具有独立证据价值，无需重复运行同一路径。
2. 在 PowerShell 中设置 `$env:PYTHONDONTWRITEBYTECODE = '1'`；使用**新的空合成目录**作为 `--data-root`，而非候选包里的 `data`。
3. 启动：
   ```powershell
   $env:PYTHONDONTWRITEBYTECODE = '1'
   & 'D:\SRW\candidate-d8d032d\windows-host\SmartRecruitmentWorkbench.exe' --application-root 'D:\SRW\candidate-d8d032d' --data-root 'D:\SRW\synthetic-workspace'
   ```
4. 验证：WPF 窗口能启动、WebView2 页面有数据、项目创建及候选人模拟收件可用、关闭窗口后无残留后台进程和锁冲突。**不要使用任何真实候选人信息。**
5. 如果 GUI 报错或关闭：提供 `Get-Content 'D:\SRW\synthetic-workspace\logs\host.log' -Tail 100` 的输出（检查并遮蔽任何不希望共享的本机路径）。
6. 若希望复现静态审计，而已经被首次运行修改了缓存状态，**首选将原 ZIP 解压到一个新目录**后，用新版脚本和**全新**的证据文件名运行；不要删除旧通过证据，也不要在不明确新增文件身份的情况下清理数据。通过运行初始 ZIP 哈希进行归档对照。

## 当前发布门槛

Windows 嵌入式 Python 与实际后端：**实机通过（用户提交的真实 JSON）**。Windows WPF/WebView2 GUI、OCR/ASR、AI Provider 降级、完整招聘运营与备份恢复：**尚待目标机器验收**。只有本地完成后续 GUI 操作并拿到可审查日志/截图，才可升级发布状态。
