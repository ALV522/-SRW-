# SRW Windows Native Runtime/Knowledge：工件保管与独立重建（Issue #124）

状态：P0 产品化阻断；审计源码 main df944cdfd195a07aa15c834dfcab79b831f7a114（2026-10-26）。后续实时状态与 PR CI 以 GitHub 当前 HEAD 为准。此文件是行动计划，不是灾难恢复验收凭证。

## 1. 事实与风险分级

| 对象 | 已有证据 | 未解决风险 |
|---|---|---|
| 原 alpha10 Web Runtime | 历史 1,611 文件、约 99 MB；原始依赖只有 5/13 与 C11 pin 匹配 | 旧材料，不等于当前 Native 运行时 |
| 固定 d8d032d Prepared Native ZIP | 101,617,623 字节；SHA-256 27ae4765c035d7855ef69829256eaf33038362e0b28354b6af372c6d2304b2cb；包含 2,332 个 Runtime 文件和 5 套 Knowledge DB | 原始 ZIP 字节不在 Git；唯一外部副本一旦丢失，源码和哈希不能恢复内容 |
| C11 Python | overlay 优先于 legacy site-packages，依赖元数据 13/13 匹配；0cbd 候选已在 Windows 完成 13 项真实模块导入和 Backend smoke | 不证明无历史 ZIP 独立重建、供应商来源、最新 SHA GUI |
| Source/WPF Host/Wheelhouse | Source manifest、Git SHA、Host 来源绑定、Ubuntu/Windows Source/Chromium CI；Windows wheelhouse 自动下载/安装/导入 | Wheelhouse 保留 30 天，版本 pin 不是完整传递 wheel 的字节锁 |
| 五套 Knowledge SQLite | 文件 SHA、结构表校验及 SQLite 完整性核查 | 尚须逐库厘清上游种子、许可、可重建性、合法分发与异地保管 |

结论：原批评中的 1,611/5/13 属历史、不同输入；不能说当前 Native 仍 5/13。但唯一外部 ZIP 是真实 P0 保管与发布连续性风险。SHA-256 证明字节一致性，不证明永久可获得、来源可信、合法分发或灾难恢复成功。

## 2. 权威源码与工件入口

- 固定旧 ZIP 身份：scripts/rebuild_native_from_prepared.py 的 BASE_PREPARED_ZIP_SHA256，及 docs/NATIVE_PINNED_INPUT_AUDIT_20261022.md。
- 源码身份：Git main、SOURCE_MANIFEST.sha256、不可变 SOURCE_RECOVERY_MANIFEST.sha256。
- Runtime 元数据与构建：requirements-ci.txt、scripts/check_embedded_runtime_compatibility.py、scripts/upgrade_embedded_runtime.py、.github/workflows/windows-runtime-wheelhouse.yml。
- 完整 Native 校验与验收：scripts/verify_rebuilt_native.py、scripts/accept_rebuilt_native_gui.py、scripts/accept_native_business.py；真实 Windows UI/业务必须属于相同候选 ZIP SHA。
- 旧资源来源索引：docs/history/ARCHIVE_CATALOG.md 和 docs/history/LEGACY_ARCHIVES.json。两者的清单不包含原始私有二进制。

## 3. 立即治理：两份独立保管、副本可读性核验

产品负责人在两台独立设备或不同故障域保留完整的原始 Prepared ZIP，最好增加第三份受控加密离线/异地不可变副本。加密密钥须与密文分开保管；将两份文件放在同一磁盘不同目录不能称异地容灾。完整 Runtime、真实 Knowledge DB、密钥、工作区、候选人数据和 ZIP 不得上传当前 Public GitHub 或公共 Actions。

只读核验命令（请改成本机实际绝对路径）：

    py -3.12 .\scripts\audit_native_artifact_custody.py --primary D:\SRW\private\prepared.zip --secondary E:\SRW-offline\prepared.zip --evidence D:\SRW\private\evidence\custody-unique.json

核验器采用源码中固定的 SHA 和文件大小；拒绝缺失、内容不符、软链接、硬链接/同一文件、读时被修改、已有报告路径，既不解压执行也不打印私有路径。输出 TWO_PINNED_COPIES_VERIFIED_RECOVERY_NOT_PROVEN，仅说明两份文件对象可读且字节正确。即使观测到不同设备 ID，也不能自动判定独立故障域、许可或可恢复性。

真正的容灾演练需关闭原始 ZIP 路径，隔离干净 Windows 环境，使用异地副本重新执行完整装配、全部文件核验、嵌入 Python 导入、Backend smoke、真实 WPF 及合成招聘业务验收；登记新候选源码/Host/ZIP SHA、失败项与操作人员。建议季度抽查和重要发行前重演。未经完整演练不能提升到 RECOVERY_PASS。

## 4. 中期去掉唯一历史 ZIP 依赖

**软件 Runtime（Track A）：** 锁定官方 Windows Python embeddable ZIP 的版本、平台、URL、实际分发者签名和 SHA；锁定每个传递依赖 wheel 的文件名、来源、SHA、ABI、许可证（不仅是 13 个顶层版本），通过离线 hash 校验安装。对 .NET、WebView2、Host 构建输入建立单独 BOM / SBOM / 构建证明。30 天 CI artifact retention 不能当唯一存档。干净 Windows 从受审查来源独立组装后，区分可功能性重新构建与位级完全相同。

**Knowledge 五库（Track A 调查、负责人授权）：** 每库建立逻辑名称、参考 SHA、源数据/版本、使用许可、Redistribution 权限、导入转换步骤、Schema、是否合法从公开种子重建。可重建者保留合法 recipe；不可重建或不可公开者保存在加密、权限受控、异地多副本且经过恢复演练的私有仓库。合成 Knowledge fixture 只能给 CI，不能冒充生产库。

**发行门禁（Track A）：** 固定源码/Host/Runtime/Knowledge/完整包 SHA、依赖来源与许可、独立存储审计、至少一次 clean-room 恢复演练；在目标 Windows 上进行该准确工件的 GUI、核心招聘业务与备份恢复验收。公共 Git 只储存不敏感配方/校验元数据，未经许可不得把生产数据库或历史 ZIP 放入 Public Releases。RC/GA、许可及公开发行属于负责人裁决。

## 5. 工程顺序与并行所有权

- Track A：#123 Source 下载/PDF 页渲染内容哈希边界；#124 私有二进制字节保管与无历史 ZIP 重建供应链。
- Track B：#121 真实 Chromium 取消恢复/重启正反例，必须读取 Source 实际内容，不可只依赖审计；从最新 main 更新 Source Manifest，不自行合并。
- Track C：#43 单一 Core 的 Lease、Session、恢复时序只读合同，不改 A 的 Core/Host。

本 PR 仅新增无隐私输入的双副本校验器及合成测试、此文档和 README 导航，不改生产 Schema/Core/WPF、不提交历史私有字节。仅 exact-head Ubuntu/Windows Source、Chromium、Governance/完整性全绿且主线无漂移后才能合并。