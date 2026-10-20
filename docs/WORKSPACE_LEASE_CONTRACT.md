# SRW 工作区单写者租约合同 · `data/app.lock`

状态：**ACTIVE（源码级实现）**；对应 Issue #43 / DUAL_CARRIER_PLAN D1、ADR-0001。
本文件描述**已经存在于源码中的契约**，不声明 Windows GUI、双端并发或发行验收通过。

## 1. 这条合同解决什么

SRW 一个工作区只允许一个权威写入者。在该合同落地前，两个载体的互斥方式是**不对称**的：

- Windows Host 用 `data/app.lock` **目录**做原子创建（`CreateDirectoryW`），目录内 `instance.json` 记录属主；
- 本地 HTML/Browser Core 写的是另一个文件 `data/.srw-instance.lock`（字节区间锁），并且在启动时**看一眼** `app.lock` 是否存在。

"看一眼"不是互斥。若浏览器 Core 先启动，Host 随后启动时 `app.lock` 目录并不存在，`CreateDirectoryW` 会成功，于是两个进程同时持有同一个 SQLite 的写句柄——这正是 A5/B3 要防止的数据损坏路径。

现在两侧竞争**同一个路径、同一个原子原语**：
浏览器侧改用 `os.mkdir` 创建同一个 `data/app.lock` 目录，Host 侧无需改动（`CreateDirectoryW` 自然失败并抛 `INSTANCE_ALREADY_RUNNING`）。

## 2. 磁盘格式

```
<workspace>/data/app.lock/            # 锁目录本身即锁；创建/删除都是原子的
<workspace>/data/app.lock/instance.json
```

`instance.json` 为 schema v2，字段名与 `desktop/SRW.Desktop/Workspace/WorkspaceLease.cs`
的 `LeaseMetadata` **逐字一致**（`convergence_tests/test_workspace_lease.py` 断言完整键集）：

| 字段 | 含义 | 浏览器侧写入值 |
|---|---|---|
| `schema_version` | 租约格式版本 | `2` |
| `pid` | 持锁进程 | `os.getpid()` |
| `port` | Core 监听端口 | 实际端口 |
| `version` / `release_id` | 产品身份 | 读 `VERSION` / `BUILD_INFO.json` |
| `instance_id` | 本次租约唯一标识 | `uuid4().hex` |
| `session_id` | 会话标识 | 默认空串 |
| `edition` | 载体 | `local-web` 或 `windows` |
| `started_at` | 取得租约时间（UTC ISO） | 当前时间 |
| `process_started_at_utc` | 进程启动时刻 | **`null`**（见 §5） |
| `hostname` | 主机名 | `socket.gethostname()` |
| `data_dir` | 绝对数据目录 | 绝对路径 |
| `data_root_hash` | 数据目录哈希 | `sha256(normcase(abspath))` |

## 3. 竞争与恢复规则（全部 fail-closed）

| 观察到的状态 | 判定 | 行为 |
|---|---|---|
| 路径不存在 | `absent` | 创建租约 |
| `app.lock` 是符号链接 | `foreign` | **拒绝**，不跟随、不删除 |
| `app.lock` 是普通文件（历史/异种写法） | `foreign` | **拒绝**，保留原字节 |
| 目录存在、无 `instance.json`，年龄 < 5s | `active` | **拒绝**（视为另一载体正在初始化） |
| 目录存在、无 `instance.json`，年龄 ≥ 5s | `stale` | 重新检查后删除并重试一次 |
| `instance.json` 不可解析 / 无可用 `pid` | `corrupt` | **拒绝**，不静默覆盖 |
| `pid` 对应进程存活 | `active` | **拒绝**，报出载体与 pid |
| `pid` 对应进程已消失 | `stale` | 重新检查后删除并重试一次 |

两条补充约束：

1. **恢复前二次确认。** 删除 `stale` 租约前重新读取一次；若期间 `instance_id` 变化则放弃删除，避免误删刚建立的租约。
2. **只释放自己的租约。** `release()` 仅当磁盘上的 `instance_id` 与本实例一致时才删除，绝不驱逐他人租约（有专门回归）。

## 4. 两个锁，固定顺序

浏览器入口仍先取 `data/.srw-instance.lock`（`scripts/launch_alpha10.InstanceLock`），再取 `app.lock` 租约：

- `.srw-instance.lock` 只为兼容**更早的 alpha10 Portable**（它只认识这个文件），避免老实例与新 Core 同时写；
- `app.lock` 是跨载体权威租约。

顺序固定为"先 legacy、后租约"，因为 Host 从不取 legacy 锁，不存在反向加锁导致死锁的路径。

## 5. 已知不对称：`process_started_at_utc` 写 `null`

C# 侧 `IsSameProcessInstance` 对缺失的进程启动时刻采取**保守**分支（视为存活）。
如果浏览器侧写入一个与 .NET `Process.StartTime` 相差超过 1ms 的值，C# 会判定为"不同进程实例"并**删除仍在使用的租约**，从而造成双写——这比不做 PID 复用检测更危险。
因此浏览器侧写 `null`：存活判断退化为单纯的 PID 存活检测（fail-closed），代价是 pid 被复用时可能短暂阻塞，需要人工清理 `data/app.lock`。此取舍记录在此，不隐藏。

## 6. 适用范围与仍未覆盖的部分

**已由源码回归覆盖**（`convergence_tests/test_workspace_lease.py`、`test_start_local_web.py`）：
同工作区第二写入者被拒、Host 形态存活租约阻止浏览器 Core、崩溃进程租约可恢复、新鲜无元数据目录不被误删、普通文件锁不被覆盖、损坏元数据不被静默替换、只释放自己的租约、无租约时不创建目录。

**明确未覆盖，不得据此宣称通过**：

- 真实 Windows WPF Host 与浏览器 Core **同时运行**的双端验收（需要目标机与工件，属 #43 后续里程碑 M3）；
- Core Supervisor、事务级 CAS、会话附着、后台任务唯一所有权（D1 的其余部分）；
- `scripts/run_local.py --workspace-lock backend` 仍未取租约；该入口目前只被 Host 以 `--workspace-lock host` 调用（Host 已持租约），独立使用该入口属已知缺口；
- 浏览器 Chromium 业务回归不覆盖本合同。

## 7. 回滚

租约文件名与格式沿用了 Host 既有实现，因此回滚本改动不会让旧 Host 读到未知格式：旧浏览器入口恢复为"只看 `app.lock` 是否存在"，即回到已知的双写竞争状态。回滚应按 `docs/RELEASE_PROCESS.md` 走代码回退，不需要数据迁移，也不应手工删除用户工作区的 `app.lock`。
