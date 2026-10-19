# C11 Windows Native 候选包：从已核验 d8d032d 逐版装配

> **交付性质**：本页面提供实际可运行的 Native **候选包装配路径**，不是直接发布经过用户实机验收的正式产品。新候选包命名必须保留 `UNVERIFIED_GUI`，所有数据操作必须在新的、独立的工作区进行。

## 交付目标

过去 Windows CI 分别发布 C11 源码和 Host 编译产物，无法直接用于新版完整桌面程序。而此前的 `d8d032d` **完整 Prepared Native** 已包含：

- Python 3.12 Embedded Runtime + 经锁定的 C11 依赖 Overlay；
- 完整五套 Knowledge 数据库，以及独立记录的 SHA-256 manifest；
- 已经过静态文件审计和基础实机 GUI 验收的 WPF/后端来源；
- 但其 C11 **业务源码是旧提交**，不能代替现在的招聘业务闭环。

新的路径不是复制旧源代码：使用 **当前 main 的全部 manifest-tracked 源码、由同一 Git SHA 编译的 WPF Host**，只从精确旧 ZIP 恢复已经核验的 Runtime/Knowledge。然后将新组合产出独立 ZIP，重新做全部文件校验。

## 一个 CI 工件替代两个分散的输入

打开 [SRW Windows Host Rebuild Candidate](https://github.com/ALV522/-SRW-/actions/workflows/windows-host-candidate.yml)，在**最新成功的 main 运行**中获取 Artifact：

`srw-c11-native-upgrade-kit-<40-char SHA>-NO-RUNTIME-NOT-RELEASE`

这是 GitHub Actions **工件压缩包**，其中包含第二层真正的：

`SRW_C11_NATIVE_UPGRADE_KIT_<SHA>_NO_RUNTIME.zip`

将第二层 ZIP 完整解压到新的文件夹，例如 `D:\SRW\upgrade-kit-<SHA>`。它含：

```text
BUILD_C11_CANDIDATE.cmd
SOURCE_KIT_README.md
SOURCE_KIT_PROVENANCE.json
SOURCE_MANIFEST.sha256
VERSION
scripts/
backend/
frontend/
desktop/
windows-host/
  SmartRecruitmentWorkbench.exe
  HOST_BUILD_CANDIDATE.json
  DOTNET_BUILD_TRUTH.json
```

这个工具包 **没有 Runtime、没有五套 Knowledge、不含真实候选人记录，不是可以直接双击运行的新版 Windows 完整产品**。

## 你需要提供的唯一历史外部输入

精确的 `SRW_C11_Windows_Native_PREPARED_UNVERIFIED_GUI_d8d032d.zip` 原始 ZIP，固定身份：

| 属性 | 精确值 |
|---|---|
| 来源 Git 提交 | `d8d032de255c87839adbeedc5737124d7fbfc3cd` |
| ZIP SHA-256 | `27ae4765c035d7855ef69829256eaf33038362e0b28354b6af372c6d2304b2cb` |
| 原始 ZIP 字节数 | 101,617,623 |
| 使用目的 | **仅**从经核验 ZIP 提取 Runtime 与生产 Knowledge；**不用**其中的旧业务源码 |

需要的是原始 ZIP，而不是 `D:\SRW\candidate-d8d032d` 中已经运行过、可能生成 `__pycache__` 的解压目录。任何非精确 SHA 的旧 ZIP 均会拒绝装配，**禁止重新计算哈希来绕过约束**。

## Windows 本机生成新 Native 候选

系统要求：Windows 10/11 x64、安装 Python 3.12（用于**装配**；新候选包自带旧核验 Runtime）。以后运行程序另需 .NET 10 Desktop Runtime 与 Edge WebView2 Runtime。

打开新解压的 kit 文件夹中的 CMD，执行：

```bat
BUILD_C11_CANDIDATE.cmd "D:\SRW\SRW_C11_Windows_Native_PREPARED_UNVERIFIED_GUI_d8d032d.zip" "D:\SRW\SRW_C11_new_UNVERIFIED_GUI.zip"
```

装配器通过 `scripts/rebuild_native_from_prepared.py` 严格执行：

1. 验证旧 Prepared ZIP 的固定 SHA，而不是接受调用者指定的新值；
2. 读取原有 Runtime/Knowledge manifest，逐成员检查压缩包路径、类型、重复条目、字节数、SHA；只提取选定 Runtime 和五库；
3. 使用 `PRAGMA quick_check` 校验每套 SQLite Knowledge 与所需业务表；
4. 检查 Runtime 中有效 Python 包版本严格满足**当前 C11** 的 `requirements-ci.txt`（不可自动切换为旧版要求）；
5. 用 `SOURCE_KIT_PROVENANCE.json` 或当前 Git HEAD 校验新源码版本，再验证 WPF Host 的源码 Git SHA、EXE 哈希及编译真相文件；
6. 调用仓库已有的 `build_native_from_source_host.assemble` 生成新的候选 ZIP，验证全部成员 SHA 和白名单；若目标文件已存在，则不覆盖。

仅想核查旧 ZIP/Runtime 和当前 Host 输入是否匹配，可运行：

```bat
py -3.12 scripts\rebuild_native_from_prepared.py --source . --host windows-host --base-zip "D:\SRW\SRW_C11_Windows_Native_PREPARED_UNVERIFIED_GUI_d8d032d.zip" --verify-only
```

失败会输出 `{"status":"BLOCKED", ...}` 并返回 exit code 2，不修改旧 ZIP、不打开现存 SRW 数据库、不生成新版发布声明。

## 下一道实际产品验收

生成新的 `UNVERIFIED_GUI.zip` 后，解压到**全新目录**，例如 `D:\SRW\candidate-<newsha>`，不要覆盖 `D:\SRW\candidate-d8d032d`。

先按 [Prepared Windows Native 静态/后端验证](PREPARED_NATIVE_WINDOWS_ACCEPTANCE.md) 中的命令，在包外生成唯一命名的验收 JSON；然后使用独立合成 `--data-root`，以实际 WPF EXE 启动：

```powershell
& "D:\SRW\candidate-<newsha>\windows-host\SmartRecruitmentWorkbench.exe" `
  --application-root "D:\SRW\candidate-<newsha>" `
  --data-root "D:\SRW\synthetic-workspace-<newsha>"
```

人工验收顺序为：正常启动/关闭、项目与岗位、Criteria 发布、Source/Claim/人工核实、Decision 失效与重申、独立面试 Scorecard、Offer 业务状态、重复启动、文件锁/缓存、自有数据隔离；最后才安排经授权的脱敏样本及 Provider/OCR/ASR 真实链路。

**CI 的 Host 编译、7 条 Chromium/SQLite 业务测试以及装配 ZIP 校验不构成这份 Windows GUI 全业务 PASS。** 如果后续测试失败，记录具体新工件 SHA 和证据，不修改原旧包。正式 RC/GA 必须另走 [RELEASE_PROCESS](RELEASE_PROCESS.md)。

## 后续演进

本次是用户可实际执行的 **Native 升级和候选交付链**。下一步是让合成 Windows GUI 业务验收脚本跑完整 C11 七大动作，并逐步将 CI 装配器引入正式带签名的产品发布流程。等正式主线 Native 候选业务稳定，才将 E3/E4/E5 探索中的 Core CAS/独立进程/受保护附着迁移到正式 Web+EXE 双载体。
