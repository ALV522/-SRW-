# 从旧版 ZIP 恢复 C11 外部依赖（2026-10-18）

## 审计结论

**不应再把 Runtime 和五套 Knowledge 一概列为“找不到”**。本次逐一打开用户提供的四个原始 ZIP，包括 v0.8.10 Assembler 内嵌的 Application Overlay；得到以下结果：

| 组件 | 旧版来源 | 本次检查 | C11 生产就绪？ |
|---|---|---|---|
| Windows Python 3.12 Runtime | alpha10 Web Portable，`runtime/` | 1,611 个文件，99,144,143 B（解压前文件体积之和）；`python.exe`、`python312.dll`、`python312._pth` 等在内 | **否**，依赖版本尚需修复、Windows 实际加载未测 |
| Taxonomy DB | v0.8.12-R2 `knowledge/active/` | SQLite `integrity_check=ok`，786,432 B | 数据内容与来源仍须业务核验 |
| Job Info DB | 同上 | `ok`，2,486,272 B | 同上 |
| Competency DB | 同上 | `ok`，2,125,824 B | 同上 |
| Market Reference DB | 同上 | `ok`，434,176 B | 同上 |
| Reference DB | 同上 | `ok`，216,924,160 B | 同上 |
| WPF/WebView2 Windows Host 二进制 | v0.8.10 Assembler 及四份原包 | 只找到 **Host 源码/Application Overlay**，未发现 `windows-host/SmartRecruitmentWorkbench.exe` 的已编译工件 | **否**，需要 v0.8.8 精确 Windows Portable 载体，或重新编译 Host 并实机验收 |

数据库还与 v0.8.10 Source、alpha10 Web Portable 中同名五套 DB 的 SHA-256 全部一致，共 15 次独立 ZIP 来源内的 SQLite 完整性检查均返回 `ok`。这是完整性证据，**不是第三方真实性、隐私或许可证保证**。

原始来源 SHA-256：
- alpha10 Web Portable：`92deadadc861673fd762a8453cc0877ff21a16f5e1ea12e6172fdb2b1e6929d4`
- v0.8.12-R2 Source：`80b3b2d68de23c04d9e5a62d9701d716ee89d4ea71f7041c34d728fb1e267fb3`

恢复出的 DB SHA-256 分别为：
- `taxonomy`：`9fc9183b0450924d8e29eb3534485ae39dea828992d6e41aac3b857ec0cb7dc5`
- `job_info`：`59bf5cb394a59597e5c05b7dcd727ad33c1190a5ef1512c59e423414c3ed2d17`
- `competency`：`b9cc9890c7a544aa5f13fd4cd4e8aa4ebfa57039c3579bb7a16f1b57f334d563`
- `market_reference`：`32e58df7572d11913e99b4806519760a3fb102c90aebc243e1e5c7c324e085c1`
- `reference`：`f7ad00899e1d9996e7b0f12569ec6e4e4c9355f9674a74ae8e9e69877c5bfd31`

## 当前恢复包与复核方式

用户本次可以下载 `SRW_C11_Legacy_External_Inputs_RECOVERED_UNVERIFIED.zip`（单独交付，不作为 GitHub Release）。其中有 `runtime/`、`knowledge/active/`、`PRODUCTION_RUNTIME.sha256`、`PRODUCTION_KNOWLEDGE.sha256`、`RECOVERY_AUDIT.json`。

也可以不使用成品压缩包，直接在 C11 源码根目录运行：

```powershell
py -3.12 scripts/recover_archived_external_inputs.py --runtime-zip "D:\Archives\SRW_v1.0-alpha10_Recruitment_Operations_Web_Portable(1)(2).zip" --knowledge-zip "D:\Archives\SRW_v0.8.12-R2_Truth_Closure_Source(1)(2).zip" --output "D:\SRW\C11-external-recovered"
py -3.12 scripts/check_embedded_runtime_compatibility.py --runtime "D:\SRW\C11-external-recovered\runtime"
```

提取器要求原始 ZIP 字节与 `docs/history/LEGACY_ARCHIVES.json` 的 SHA-256 和大小一致；仅选择运行时文件与五份 DB；不执行旧包内脚本、不覆盖已有工作目录。**从旧包验证哈希生成的新清单只是经固定来源重建的清单，不等于独立供应链审计。**

原 alpha10 包里有 `certifi/cacert.pem`，这是公开 CA 根证书，不是私钥。Native 白名单现在只允许这一条特定路径的 `.pem`，仍拒绝其他 PEM、Key、PFX 和私人数据。

## 实测依赖差异：为何仍不能直接宣传为 C11 可运行

C11 当前 `requirements-ci.txt` 严格锁定 13 项依赖。旧 alpha10 Runtime 只有 **5 项版本完全匹配**、**8 项缺失或不匹配**：

| 依赖 | 旧 alpha10 | C11 要求 |
|---|---|---|
| anyio | 4.14.2 | 4.15.1 |
| click | 8.4.2 | 8.5.0 |
| idna | 3.18 | 3.20 |
| psutil | 缺失 | 7.2.2 |
| PyMuPDF | 1.26.4 | 1.28.2 |
| SQLAlchemy | 2.0.43 | 2.1.5 |
| Starlette | 0.47.3 | 0.52.1 |
| Uvicorn | 0.35.0 | 0.54.0 |

`certifi`、`h11`、`httpcore`、`httpx`、`typing_extensions` 的版本一致。需在 Windows 上对照当前锁文件升级相关 Python 包，重建 Runtime 哈希清单，再执行本机 Python `--version`、依赖加载、C11 启动、OCR/PDF 测试和外部 Provider 降级测试。原始旧 Runtime 保留为只读参考，不建议直接在原目录 `pip --upgrade` 覆盖混用不同版本。

## Windows Host 的两条路径

**A. 最短复用历史版本**：若用户还有 `SRW_v0.8.8_Windows_Portable.zip`，将其重新上传或放到 Windows 构建环境。必须命中旧载体 SHA-256 `f12933a1f6639168911af3788d207ced521be8a50841d7d39e7a2169eed3d5ab`，且内含 `windows-host/SmartRecruitmentWorkbench.exe` 和 `DOTNET_BUILD_TRUTH.json`。此前上传的是 v0.8.10 **Assembler**，不是这个完整运行载体。

**B. 无需旧二进制重新编译**：新增 `.github/workflows/windows-host-candidate.yml`，在 GitHub Windows Runner 使用 `global.json` 锁定的 .NET SDK、NuGet 锁文件从 `desktop/SRW.Desktop` 编译新 `win-x64` Host，并输出候选 EXE、SHA 与 provenance。它不是 v0.8.8 的精确继承物，不能谎称继承验证；需要单独装配、测试 Host ABI、WPF/WebView2 图形界面和启动/停止后的资源释放。当前构建路线在 CI 中验证，验证失败前不得标注为已编译成功。

## 用户目前需要做的事

**当前不必再上传这三份已有 Knowledge/Runtime 旧包**，也不必替系统手工挑选数据库文件。只有当优先保留历史 **已验证宿主二进制** 而不是重新编译时，才请用户上传原始 `SRW_v0.8.8_Windows_Portable.zip`；如果找不到，可以先走源码重编译路线，不影响继续开发。

到目标 Windows 机器测试时，需要 Windows x64、WebView2 Runtime 和 Microsoft .NET 10 Desktop Runtime（当前候选 Host 构建为 framework-dependent），或者之后将 Host 调整为 self-contained 构建。届时再运行合成候选人工作流、备份恢复、文件导入、OCR/ASR 和 Provider 降级，取得实机验收证据。

**本次工作的事实边界：外部资源已恢复且静态校验通过，但 Native Windows 安装包尚未完整生成，Host 和 Runtime 的运行兼容性仍待验证。**
