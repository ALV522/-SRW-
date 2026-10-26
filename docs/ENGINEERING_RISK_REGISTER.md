# SRW 核心工程风险地图（2026-10-26 初版）

| 风险 | 优先级及失效模式 | 可执行证据 / 主要动作 | 状态及 owner |
|---|---|---|---|
| #130 pre_restore / crash journal | P0；掉电或重启期间清理旧 DB/Blob、错误生成二次 undo 可能导致原数据损坏 | A0–A10 进程强制终止、同合成工作区连续重启、原快照 hash/完整性 oracle | 设计风险，事务代码未实现 / A |
| #128/#129 ZIP 发布 | P0；中断留下合法文件名、同名覆盖、FS 不支持硬链接、AV 锁误报 | B 两条 RED；A #129 新 HEAD 两 OS 413 GREEN（但尚未与 B 测试合流） | 实际修复 CI PASS，merge/G1 阻断 / A+B |
| #131 备份下载 | P1 可升级；FileResponse path TOCTOU、恶意替换或 in-place 修改、512 MiB 大包 RAM 限制 | 先设计 validated open handle / bounded disk snapshot，测 Range/Win 共享/竞态 | 待复现 / A |
| #43 会话/敏感 GET | P0；loopback+Origin 不抵御同机其他进程，现有 info 泄露 instance/session 工作区标识 | opt-in gate，匿名最小白名单、真实 HTTP 401/403/Host attach/revoke 和双端互通 | 尚未实现 / C+A |
| #124 Runtime/Knowledge | P0 发行可复现性；外部 private 依赖不具真正双故障域完整保管 | pins 与 five-DB 授权、第二故障域 restore、clean-room 上游重建 / 真机验证 | BLOCKED / A |
| #43 同工作区双端/lease | P1；重复 writer、Job owner、CAS 412 假审计、恢复互锁 | T1–T10 及 WPF/Browser 并发/故障注入 | 未全面验收 / A+C |
| #120/#122/#127 Evidence | P1；Source 内容/路径被篡改可能误导 HumanDecision | 已有 SHA/immutable bytes 的局部生产修复，继续路径负例 | 部分已修，不能外推全 Evidence PASS / A |
| #132 审查与清单 | P1/P2；单作者自合/无 branch protection、全局清单 merge 冲突 | 非作者轨道 Review、preflight 证据、只读差异报告、后续分目录实验 | 临时人为门禁 / A+B |

**执行规则：** P0/P1 的可复现缺陷先固定 RED 再修复成 GREEN；真实掉电必须杀进程而不是异常捕获；设计阶段同时检查 Windows/POSIX 的 `os.link`、`fsync`、路径/文件锁、SQLite WAL/SHM 和持久化点。任何新 CI SUCCESS 仅归属于该 Git SHA；Native/生产 Knowledge/Provider 各自记录 PASS/NOT RUN。每次完成 M1 里程碑后评估这些风险的状态和回归资产，不自动删除历史工件。
