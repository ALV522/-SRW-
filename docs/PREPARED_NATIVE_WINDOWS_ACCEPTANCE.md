# C11 Prepared Windows Native ZIP · 独立实机验收（2026-10-19）

## 已取得的实物

本次不是只交付源码：已从同一 Git 提交 `d8d032de255c87839adbeedc5737124d7fbfc3cd` 下载全部三个 GitHub Actions 工件（源代码、Windows Host、13 个 Windows 轮包），与用户既有的历史恢复 ZIP 合并：

- 工件名称：`SRW_C11_Windows_Native_PREPARED_UNVERIFIED_GUI_d8d032d.zip`
- 字节数：`101617623`
- SHA-256：`27ae4765c035d7855ef69829256eaf33038362e0b28354b6af372c6d2304b2cb`
- 已核验源码：**273** 个源文件
- 已核验 Runtime：**2332** 个文件（包括 `Lib/c11-overlay` 中 Windows Wheel）
- 已核验 Knowledge：五套历史数据库、全部 SQLite `quick_check=ok`
- 已核验 Host：编译好的 Windows WPF/WebView2 Host，EXE SHA 与同 SHA 的 `HOST_BUILD_CANDIDATE.json`、`DOTNET_BUILD_TRUTH.json` 相符。
- 最终 Native ZIP：经 `scripts/native_payload.py audit_zip` **2629** 个文件白名单与 SHA-256 全通过。

**准确状态**：`OFFLINE_WHEELS_STAGED_NEEDS_WINDOWS_EMBEDDED_SMOKE` 和 `UNVERIFIED_GUI`。13/13 锁定 Python 依赖在静态版本检查中通过；**这不等于已在 Windows 上运行该嵌入式解释器**。

## Windows x64 实机验收

使用 Windows 10/11 x64；需安装 .NET 10 Desktop Runtime、Microsoft Edge WebView2 Runtime。将 ZIP 解压到不含真实招聘数据的单独目录，例如 `D:\\SRW\\candidate-d8d032d`。请勿把它直接解压覆盖旧工作台或旧数据目录。

从当前 [GitHub 主线](https://github.com/ALV522/-SRW-)克隆/更新源码，使用外部 Python 3.12 启动新验收程序。**新验证程序可以来自后续提交，但候选 ZIP 内的源码/Host 身份仍必须是原 `d8d032d`，不要将两者混合重封包。**

```powershell
py -3.12 "D:\\SRW\\source\\scripts\\verify_prepared_native.py" `
  --root "D:\\SRW\\candidate-d8d032d" `
  --evidence "D:\\SRW\\evidence\\C11-prepared-Windows-smoke.json"
```

该工具执行以下实际步骤：

1. 校验所有发布清单中的源码、Runtime、Knowledge、Host 和全部额外文件清单；拒绝修改的 DLL、未列明的候选人数据、密钥和符号链接。
2. 校验 `python312._pth` 加载优先级，确认十三项依赖有效版本。
3. 在 Windows 真正运行候选包内 `runtime/python.exe -I`，导入 13 项 C11 Python 包，并要求导入路径局限于候选包 Runtime。
4. 使用**临时空工作目录**、合成 Host 身份、只绑定 `127.0.0.1` 启动候选包内真实 Python 后端；等待 `/api/v1/runtime/ready`；校验 `/api/v1/runtime/info` 的 WPF Host ABI 身份；优雅退出/强制回收测试进程。
5. 验收日志写到用户指定的、**候选包目录之外**的 JSON 文件，不修改发布包，也不动真实用户数据。失败返回 exit code 2；运行成功仍会注明 `wpf_webview2_gui_accepted=false`。

若需要先检查离线文件，而非在 Windows 上执行，则增加 `--static-only`；这一模式生成 `STATIC_PASS_WINDOWS_SMOKE_PENDING`，**不可用作实机验收证据**。

## 图形界面验收（必须单独完成）

上述脚本检查真正的 Windows Python 和后端 Host ABI，**不会虚构用户点击或 WPF 实机成功**。Windows 运行验收通过后，用新的合成工作目录启动原生程序：

```powershell
& "D:\\SRW\\candidate-d8d032d\\windows-host\\SmartRecruitmentWorkbench.exe" `
  --application-root "D:\\SRW\\candidate-d8d032d" `
  --data-root "D:\\SRW\\synthetic-workspace"
```

核对 GUI 启动/退出、WebView2 页面、候选人和岗位 CRUD、材料导入、OCR/ASR、Provider 降级、备份恢复以及进程退出后无锁文件占用。**完整 Windows Native Release 的发布还需要这份 GUI 证据；不能将无窗口后端 smoke 当成已经通过实机 GUI。**

## GitHub 工作流与身份边界

- [当前源码/自动测试](https://github.com/ALV522/-SRW-/actions/runs/39148139262)
- [当前 Windows Host](https://github.com/ALV522/-SRW-/actions/runs/39148139267)
- [当前 Windows Wheelhouse](https://github.com/ALV522/-SRW-/actions/runs/39148139264)
- [当前浏览器业务验收](https://github.com/ALV522/-SRW-/actions/runs/39148139326)

这是过渡性的**完整待验收候选包**，并非可公开宣传的稳定 Windows Portable。GitHub 的源码回归、Windows Host 编译及 Wheelhouse 导入通过均是必要证据，但它们不能替代目标机的真实 WPF/WebView2 验收。

## 首次 Windows 实机结果与重跑修复（2026-10-19）

2026-10-19 用户实际执行 `verify_prepared_native.py` 于 Windows：embedded Python 3.12.10、13/13 依赖、隔离 loopback backend readiness、Windows Host ABI 均 PASS。首次 JSON 仍保持 `gui_accepted=false`；后续同一目录重复检查提示未知额外/缺失文件，怀疑 Python 导入时自动写入 `__pycache__`。已通过新版源码将 import/后端 Python 启动改为 `-B`，WPF 新 Host 使用同样选项，增加具体文件差异和重复证据文件名拒绝。请保留首次 JSON，继续进行 GUI 验收并提供 Host 日志。详细见 [WINDOWS_FIRST_SMOKE_RESULTS](WINDOWS_FIRST_SMOKE_RESULTS.md)。
