# SRW 核心工程风险地图（2026-10-27 刷新）

> 这是**带时间点的快照**，不是实时状态。每条都写明"证据属于哪个 SHA"；合并状态、CI、PR 编号在引用前必须重新查询 GitHub，不能把本表当作当前权限或当前绿灯。

| 风险 | 优先级与失效模式 | 可执行证据 / 主要动作 | 状态（2026-10-27）与 owner |
|---|---|---|---|
| 恢复事务与崩溃窗口（#130） | P0；掉电或强杀时旧 DB/Blob 被误删、二次 undo、残留整库副本 | 真实子进程致死矩阵 + journal `PREPARED→APPLYING→COMMITTED` + pinned 目标哈希 + 幂等重解包 | **已合入 `a1e566e`（#144）**；残留 `srw-restore-*`/`srw-prerestore-*` 已纳入启动清理。未证明：Windows 突然掉电持久性；`COMMITTED` 后 AV 长期占用仍 fail-closed，独立终态合同未定义 / A |
| 备份原子发布（#139/#140） | P0；中断留下"列表可见但排程才失败"的截断档、同名覆盖、不支持硬链接、AV 锁误报 | `.srw-staging-*.partial` + 逐成员 SHA/大小 + fsync + `os.link` 不覆盖 + 列表命名过滤；两条确定性注入回归 | **已合入**（#139 → #140）。未证明：POSIX 目录 fsync 后失败的已发布状态、Windows AV 干扰 / A |
| 备份下载完整性（#131） | P1 可升级；`FileResponse(path)` 的 TOCTOU、下载中被替换/原地改写 | 有界校验快照（单 FD、1 MiB 分块、512 MiB 上限）、Range/206/400/416、finally 清理 | A 有两份离线补丁（39/39、46/46 定向），**无 PR、无远端 HEAD、preflight/CI/Native NOT RUN**；需要真实干净分支转移后才能算修复 / A |
| 会话与敏感读（#43） | P0；回环 + Origin 挡不住同机其他进程；`/runtime/info` 暴露 instance/session 标识 | 纯策略模块（默认 OFF、`X-SRW-Session`、匿名最小白名单、路径歧义拒绝、same-site 拒绝、query 键五轮解码） | **策略已合入 `cf72d6e`（#145）**；但 **middleware 未接入，真实 HTTP 仍无会话校验**；7 条 test-only `200→401/403` RED 已获 A 合同、尚未写 / C+A |
| 同工作区双端并发（#43 后半） | P1；重复 writer、Job owner、CAS 412 假审计、恢复互锁 | T1–T10 与 WPF+Browser 并发/故障注入 | **NOT RUN** / A+C |
| Native 外部工件保管（#124） | P0 发行可复现性；私有 Runtime/Knowledge 缺第二故障域 | pins 与授权、clean-room 重建、真机验证 | **BLOCKED**；仓库内无原始 Knowledge/Runtime / A |
| Evidence 读取完整性（#122/#127） | P1；Source 内容/路径被篡改会误导人工决定 | 读时 SHA 校验、immutable PDF/下载快照 | 生产修复已合入；未被证明的部分继续用负例覆盖，不外推"Evidence 全绿" / A |
| 治理与清单（#132，本 PR） | P1/P2；单作者自合、无 branch protection、全局清单冲突 | 非作者轨道 Review 协议、preflight 证据、只读清单差异报告 | 协议与只读工具随本 PR；**分支保护仍未启用**，属人为纪律 / A+B |

## 执行规则

1. P0/P1 的可复现缺陷先固定 **RED**（合成、确定性），再修复成 GREEN；真实掉电必须杀进程，不能用 `except` 模拟。
2. 每个新 CI SUCCESS 只属于它自己的 Git SHA；跨 SHA 外推等同于伪造证据。
3. 设计阶段就写 Windows/POSIX 差异表：`os.link`、`fsync`、`os.replace`、文件共享、SQLite WAL/SHM、路径大小写。
4. 无法自动复现的故障，必须写明人工/进程杀死 oracle 与未测边界，不能标注 PASS。
