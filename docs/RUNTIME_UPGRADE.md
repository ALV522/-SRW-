# C11 Windows Python Runtime：隔离升级与实际验证

本流程使用先前从 alpha10 恢复的 Windows Python 3.12 Runtime 和五套 v0.8.12-R2 Knowledge 数据库。**不会覆盖历史原包、历史 Runtime 或真实候选人数据**。这是使其满足当前 Convergence 11 锁定依赖的工程途径，不表示 Windows WPF GUI 已验收。

## 构建产物的身份

- 历史原料：`SRW_C11_Legacy_External_Inputs_RECOVERED_UNVERIFIED.zip`。原始包只作只读来源。
- GitHub Actions：[`SRW C11 Windows Offline Wheelhouse`](https://github.com/ALV522/-SRW-/actions/workflows/windows-runtime-wheelhouse.yml)，用 Windows / CPython 3.12 下载当前 `requirements-ci.txt` 的二进制 Wheel 和必要传递依赖、离线安装后在 Windows 上验证导入，再打包 `WHEELHOUSE.sha256`。
- 升级器：`scripts/upgrade_embedded_runtime.py`，对原始 Runtime 做 SHA 校验，临时装配后在 `runtime/Lib/c11-overlay/` 安装 Wheel，在 `python312._pth` 中将其放到历史 `Lib\\site-packages` 之前；用**实际嵌入式 `python.exe`** 验证关键包导入；只有全部通过才提交输出目录及新的 `PRODUCTION_RUNTIME.sha256`。
- 正式 Native 装配：`scripts/build_native_from_source_host.py` 检查 `RUNTIME_UPGRADE_AUDIT.json` 的 `C11_RUNTIME_SMOKE_PASS`、C11 依赖版本、五个数据库及 Host Git SHA，审计成品 ZIP 并继续标记 `UNVERIFIED_GUI`。

## Windows x64 操作

先通过 GitHub 克隆当前主线，保持所用 Windows Host 与 `git rev-parse HEAD` 的 Git SHA 一致。系统中需要 Python **3.12 x64（含 pip）**。下载同一源码版本对应的 Wheelhouse 工作流 Artifact 与 Windows Host Artifact。分别解压到例如：

- `D:\\SRW\\external-legacy`（旧恢复包：`runtime`、`knowledge` 与两份 SHA 清单）
- `D:\\SRW\\wheelhouse`（一组 Windows `.whl` 与 `WHEELHOUSE.sha256`）
- `D:\\SRW\\host`（与源码完全相同 SHA 的 WPF Host 候选程序和两份构建溯源 JSON）

在完整的 SRW Git 根目录运行：

```powershell
py -3.12 scripts/check_embedded_runtime_compatibility.py --runtime 'D:\\SRW\\external-legacy\\runtime'
# 上一步在未升级的原始 Runtime 上返回 C11_DEPENDENCIES_NOT_READY 是预期行为

py -3.12 scripts/upgrade_embedded_runtime.py --legacy-inputs 'D:\\SRW\\external-legacy' --wheelhouse 'D:\\SRW\\wheelhouse' --output 'D:\\SRW\\external-c11'
# 需要报告 status=C11_RUNTIME_SMOKE_PASS（不会覆盖已有 D:\SRW\external-c11）

py -3.12 scripts/check_embedded_runtime_compatibility.py --runtime 'D:\\SRW\\external-c11\\runtime'
py -3.12 scripts/build_native_from_source_host.py --root . --inputs 'D:\\SRW\\external-c11' --host 'D:\\SRW\\host' --out 'D:\\SRW\\SRW_C11_Windows_Native_UNVERIFIED_GUI.zip'
```

升级程序只允许在**新输出路径**进行，不执行旧 Runtime 的任何程序。它使用下载来的离线 Wheel、严格锁定 C11 依赖版本并实际执行新的嵌入式解释器。`source_runtime_unmodified=true` 指历史输入不被改写，并不表示已核实下载轮包的数字签名；本阶段使用 SHA-256 目录和同提交 CI 证据绑定。网络源及供应链批准仍需要单独评估。

## 验收边界

GitHub 的 Windows Wheelhouse CI 使用受控 Windows 3.12 Python 验证 Wheel 安装和导入；由于 CI 无权获取你本地的历史恢复包，**不能由 Wheelhouse CI 单独声称旧 Runtime 实际启动成功**。只有在目标 Windows 上实际运行 `upgrade_embedded_runtime.py` 并获得 `C11_RUNTIME_SMOKE_PASS` 报告，才代表当前旧 Runtime + 新 Wheel Overlay 的加载通过。

即使全部通过，仍要对解压后完整的 Native ZIP 做 Windows WPF/WebView2 运行、业务点击、备份恢复、OCR/ASR、AI Provider 降级和 GUI 资源释放验证，不得将未经实机测试的安装包标记为 RC 或正式版。
