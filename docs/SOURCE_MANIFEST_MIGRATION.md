# SOURCE_MANIFEST 结构演进约束（#132）

**当前唯一有效清单：** `SOURCE_MANIFEST.sha256`。`SOURCE_RECOVERY_MANIFEST.sha256` 为不可变历史。四领域拆分**尚未生效**。

当前根清单覆盖不止四类：`backend/`、`frontend/`、`desktop/`、`convergence_tests/`、`browser_acceptance/`、`scripts/`、`docs/`、`.github/`、`verification/`、`build-lock/` 和根文件。按 backend/frontend/tests/docs 四类直接拆，会遗漏 Windows Native/构建/治理工件，不能接受。

已有 `refresh_source_manifest.py` 从 `git ls-files -z` 逐条写入已提交文件 hash；`check_source_integrity.py` 验证路径安全、tracked set 全覆盖、历史条目保留、字节 SHA。**CI 生成候选不能自动重写并放行实际提交**。源码 ZIP / Source Recovery / version truth 也依赖清单合同。

**本轮提供只读审查命令：** `python scripts/report_source_manifest_delta.py --base-ref main`。从本地最新 main 读取基准规范清单，对比当前清单，按新增、删减、变更列出路径；不写入、不核验文件实际内容、不自动批准合并。必须另跑 `check_source_integrity.py` 并人工审查 diff。

**未来分拆验收顺序：**
1. 对所有 tracked 文件设计全覆盖且互斥的领域映射（含新根目录、Unicode/大小写/hidden 文件），先不移除根清单。
2. 在 CI 中生成子清单的**派生**输出，证明 union 与 root 完全相等；跨目录移动、删除/新增、文件损坏、软链必须 fail-closed。
3. 证明历史 C08 清单、source ZIP、release truth、Host/Native 装配和 Windows 路径语义不变；设计规范化聚合 digest 和签名/审核界限。
4. 用两个实际冲突 PR 测量减少的 rebase 成本，证明收益；做独立 ADR/小 PR 与双 OS 全门禁才考虑把子清单提升为权威。

在此之前不引入 `backend.manifest`/`frontend.manifest` 等并行真相，更不让 GitHub Action 修改 SHA 后宣称一切合法。


## 只读分域 pilot（#132）

运行 `python scripts/report_source_manifest_domains.py --markdown`：严格验证当前 Source Manifest 与全部 tracked 源字节，然后按**backend、frontend、desktop、tests（含 browser_acceptance）、docs、automation（含 .github/scripts/verification/build-lock）、root-other** 七个域导出只读 SHA-256 摘要。任意新根目录归入 root-other，不遗漏隐藏文件、中文名或构建输入。采用 canonical `sha256 + two spaces + POSIX path + LF`，全域精确合并还原权威根清单；对缺项/非规范排序/CRLF/改写内容 fail-closed。零写回、零 CI 自修复。

**这不是分域清单正式上线，也尚未解决根清单冲突。** 只是在 CI 中生成可检查的映射与稳定摘要，为后续按冲突域拆分提供硬证据。迁移到权威分片前还需要测量并发 PR 的实际 rebase/冲突时长，设计根摘要、提交级版本绑定、跨平台行尾，以及 `SOURCE_RECOVERY_MANIFEST.sha256` 历史不变和 Source/Native 消费者兼容的独立评审。

**#150 分域试点审查补充：** 该导出是非权威报告，Source Gate 中使用 `continue-on-error` 保持试点故障不会意外阻断全部开发；原 `check_source_integrity.py`、Release Truth 和业务 Source tests 仍是严格门禁。`root-other` 会列出未被识别的新顶层前缀，而不是悄悄掩盖目录扩展。
