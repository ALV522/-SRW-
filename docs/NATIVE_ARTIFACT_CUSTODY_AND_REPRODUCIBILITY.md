# Windows Native 输入保全与独立重建计划（#124）

状态：**ACTIVE P0 release work; no full independent rebuild yet.** 本文受 G1 A5/A7/A8、`RELEASE_PROCESS.md` 与 `C11_NATIVE_CANDIDATE_UPGRADE.md` 约束。公开 Git 只保留工具、哈希、构建规则和合成测试，不存储生产 Knowledge、用户资料、密钥或私有原始 ZIP。

## 1. 当前可复核事实（不是同一个历史工件）

- 历史 alpha10 Web Portable 的 1,611 Runtime 文件 / 约 99 MB 与未覆盖层的 5/13 版本匹配，不等于**现行 Native 输入**。不得把该历史扫描替换为最新 Windows 评估。
- 现有 Native 路径：源码 SHA + 同 SHA WPF Host 通过 GitHub CI 构建；从用户单独保存的**固定原始** `d8d032d` Prepared ZIP 提取嵌入式 Windows Python Runtime 和五套 Knowledge。原始 ZIP SHA-256 为 `27ae4765c035d7855ef69829256eaf33038362e0b28354b6af372c6d2304b2cb`，大小 101,617,623 字节；2,332 Runtime 文件与五份 Knowledge manifest 条目需完整一致。有效 C11 `Lib/c11-overlay` 13/13 固定包元数据匹配；实机嵌入 Python 13 项导入与后端 Smoke 是另一级证据。
- 这些检查证明一个**已有候选包的字节身份与有限执行**，不证明不同环境可以从上游重新取得原始资料。单独固定 SHA 不提供可用性、授权、原产地签名、许可证或灾难恢复能力。新的 main SHA 要重新组装和重新验收，不能复用历史 GUI PASS。

## 2. 当前阶段立即执行：独立保全两份，不触及已有招聘数据

`python scripts/audit_native_input_custody.py --primary "<原始Prepared ZIP路径>" --mirror "<另一储存介质上的独立副本>" --evidence "<新的只含状态的JSON路径>"`

- 第一份原始 ZIP 保持**只读、不重新打包、不附加缓存、不修改 manifest**。第二份由操作员复制到另一个**实际故障域**（例如不同实体磁盘、受限离线备份或经授权加密对象库）。不应把两个位于同一磁盘不同目录的文件称为独立灾备。
- 工具拒绝缺失文件、链接、同 inode/硬链接、错误大小/哈希、归档清单缺失或清单条目数量不符；不会从命令行接受新“预期 SHA”以迁就损坏文件；原 ZIP 不会被修改。失败只输出固定错误类型，不打印候选人、本地路径或二进制内容。
- **证明边界**：`PINNED_TWO_FILES_VERIFIED_FAILURE_DOMAIN_UNPROVEN` 只证明检查时两份不同文件内容精确吻合；即使两份 SHA 全绿，代码也**不能验证**不同的机房/磁盘故障域，不会写 `recovery_pass=true` 或 RC PASS。操作者须另做**第二介质离线读取**，并在隔离 Windows 机器从副本装配/校验，保留非公开、脱敏的时间戳、受控保管位置、人员职责和新的工件 SHA。
- 用户不必把两份 ZIP、生产五库或实际候选人材料交给 GitHub/Agent；如需对外交接，仅提供脱敏 JSON 和校验结果。证据文件不得覆盖历史证据；原始候选保全失败时禁止静默修改预期哈希。

## 3. 长期解除对唯一历史 ZIP 的依赖（两个并行子项目）

### Runtime（可按公开或经许可的供应链重建）

1. 固定 Windows x64 **官方 CPython 3.12 embeddable distribution** 下载源、上游签名/校验和、授权许可、文件字节及来源日期。避免依赖本地 Python 解释器的偶然版本；装配工具与可运行 Runtime 分开锁定。
2. 对 `requirements-ci.txt` 当前 13 个**直接固定版本**补完整的 Windows Wheelhouse 哈希锁（含实际转移依赖、wheel ABI、平台、原产地和 license）。版本号相同不意味着 Wheel 字节一致。原则上仅从已验证 hash 的 wheel 进行**离线安装**，记录 overlay `python312._pth` 路径优先级和启用状态，拒绝隐式网络安装。
3. 固定 .NET SDK/nuget.lock、Windows Host 编译输入和 WebView2/.NET Desktop Runtime 的外部系统前置条件；收集 SBOM、原产地元数据、解压/装配时间和准确源码 SHA。区分 reproducible **byte-for-byte** 与 rebuildable **functionally equivalent**，未实测不能宣称前者。
4. 在干净 Windows 构建机**不用旧 Prepared ZIP** 生成 Runtime，核对 13/13 元数据、导入路径、Windows Embedded Python 和六组 Core 业务 Smoke，再走完整 Native/GUI/业务回归。实现成独立 PR，不修改现有装配器 fail-closed 约束直到并行方案证明有效。

### 五套 Knowledge（不应假设能合法公开再发行）

分别为 `taxonomy`、`job_info`、`competency`、`market_reference`、`reference` 建受控清单：上游提供者、数据版本、允许的使用与再分发许可、来源/构建说明、Schema/FTS 与索引、参考 SHA-256、只读 `PRAGMA quick_check` 和升级策略。

- **许可证与来源未审计前**，不得把生产 SQLite DB 上传公开仓库、公开 GitHub Actions、公开 Release。合成 Knowledge fixture 只用于 CI，不能作为生产内容等价替代。
- 可重建且获授权的 DB：保留输入数据及确定性数据库构建脚本、SQLite 版本与语义校验；不可公开重建的 DB：使用**加密、受控、两个独立故障域**的不可变备份，定期做离线恢复演练。
- 主动区分 Knowledge 的**数据内容保真**与 Python Runtime 的依赖版本匹配；“五个数据库 quick_check PASS”不是数据来源/许可证认证。

## 4. 产品化阶段门禁与负责人事项

| Gate | 必须真实满足的事实 | 当前状态 |
|---|---|---|
| G0 源码/Host 同 SHA | GitHub Source/Windows Host CI、Source Manifest、独立工件 hash | 每次查询最新 SHA；不能把旧 PASS 外推 |
| G1 单份历史输入完好 | pinned ZIP hash/成员清单/五库 quick_check/Overlay/真实 Embedded Smoke | 已在先前 0cbd 目标机候选验证，不自动覆盖新 SHA |
| G2 存储连续性 | 两份字节级一致、**确实分开故障域**、第二份可读取 | 需要操作者执行并保存离线演练证据 |
| G3 供应链独立性 | 无原始旧 ZIP 的干净机 Runtime 重构 + Knowledge 合法恢复 | **未完成** |
| G4 当前 Windows 正式产品 | 独立 Native 完整 ZIP、真实 WPF、招聘主链、Provider/OCR/ASR、备份恢复 | **未完整完成** |
| G5 Windows/Browser 同权威 Core | 单 Workspace、同一 Core/Job/SQLite、安全会话与并发故障矩阵 | **未完成** |

技术负责人可立即执行 G2 工具/测试、发行文档和后续 Runtime 锁 PR；涉及**生产 Knowledge 原授权、是否可再分发、选择外部密钥托管与 RC/GA 决定**由产品负责人或数据权利人裁决。不得以外部单 ZIP 的 SHA 很强或 GUI 曾启动来跳过 G3/G4/G5。
