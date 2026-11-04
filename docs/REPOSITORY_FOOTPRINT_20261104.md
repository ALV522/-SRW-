# SRW 仓库与 Native 体积清点（只读、2026-11-04）

**源：** GitHub `git/trees/70756e291d79858b97f7cadc7a5b20655b6b67b7?recursive=1`，`truncated=false`。**仓库树** 437 个 blob，合计 **2,916,869 B**，没有计算 Git history、压缩率、外部二进制输入或用户工作区。根 `SOURCE_MANIFEST.sha256` 记录 436 项，其自身不入清单。无本地 Git checkout，未作实际包体测量。

## 来源归属（原始 blob 大小；不是 ZIP 内压缩体积）

| 范围 | 文件数 | 原始字节 |
| --- | ---: | ---: |
| `backend/` | 154 | 753,417 |
| `convergence_tests/` | 82 | 735,599 |
| `docs/` | 46 | 332,490 |
| `scripts/` | 32 | 272,447 |
| `verification/` | 36 | 245,050 |
| `frontend/` | 14 | 213,995 |
| `browser_acceptance/` | 6 | 122,970 |
| `desktop/` | 24 | 63,845 |
| 其余根文件、CI 与元数据 | 43 | 177,056 |
| **总计** | **437** | **2,916,869** |

**候选分离范围而非删除清单：** `convergence_tests/` + `browser_acceptance/` + `docs/` + `verification/` 共有 **1,436,109 B**，占未压缩 Git tree 约 49.2%。测试、验证历史和源身份治理需要它们；不能因运行时未 import 就从 Git 删除。当前 `scripts/build_source_archive.py`、`scripts/package_native_upgrade_kit.py` 与 `scripts/build_native_from_source_host.py` 使用完整根 Manifest 的已验证文件集合，`scripts/native_payload.py::audit_zip` 又据此验证最终 Native ZIP；单独减少打包文件会使校验失败，**不能在没有新证明的情况下裁剪**。

## 安全清理和真正瘦身的顺序

1. **本轮 README 去重：** 去除旧“最新主线事实”与多组重复的 CI 列表，保留当前任务入口、准确历史链接及已有产品说明；不删除 `verification/history/`、历史 ZIP 校验记录、G1/ADR/恢复合同或源码测试。改善的是检索和维护负担，不声称 Native 可执行包减少了多少字节。
2. **下一个独立设计/测试切片（#63 / #42）：** 先列出实际运行时需要的 `backend/`、`frontend/`、`scripts/` 和 Host 文件/配置；静态 import 只是候选列表，不等于可删证明。保留**完整 Source Manifest**用于源码审计，另建立从它派生、明确版本号、哈希和角色的候选 runtime payload 计划。针对 Source+Host kit、旧 Prepared rebuild、外部 Runtime/Knowledge、`audit_zip`、`verify_rebuilt_native`、嵌入 Python `-I -B`、Windows WPF 与双端启动加正反例，再判断是否能裁剪历史验证与构建时工具。禁止软化允许列表或凭空删掉必要模块。
3. **大头来自非仓库资产：** 旧经审计完整 Native ZIP 约 100 MB；嵌入式 Python Runtime 曾包含 1,611 个文件/约 99 MB 未压缩内容，另有 5 个 Knowledge DB 和 WPF Host。上述历史测量不是当前最终包分解。禁止把 Runtime/Knowledge 直接删除、替换为合成 DB、上传公开仓库或牺牲离线能力。优先比较受检 ZIP 各路径`file_size`、`compress_size`和 SHA、重复 wheel/site-packages、真正无依赖的包，提交**逐项删除前后功能/磁盘/ZIP 字节表**；未通过时保持当前完整 allowlist。
4. **旧文件清点：** `README_FIRST.md`、中文 `.bat` 启动别名、`SOURCE_RECOVERY_MANIFEST.sha256`、`verification/` 均可能是原始用户入口、历史还原或产物合同。本轮**不删**。只有证明无引用、保留等价迁移/回滚、双 OS Source/Native 测试和真实 Windows 操作验收后才列为删除候选。

## 验收与证据边界

本清点是 **GitHub 树元数据的静态观察**；未下载生产 Runtime/Knowledge，未运行独立 Native 构建、压缩大小比较或 WPF 人机验收。任何未来“瘦身 XX MB”须指向精确 base/new 两个 ZIP SHA-256、原始 ZIP 路径体积分布、业务操作正反例、WPF/Browser 实机分级和许可证判断。不得把源代码变少、README 变短、CI 通过解释为用户软件安装体积下降。
