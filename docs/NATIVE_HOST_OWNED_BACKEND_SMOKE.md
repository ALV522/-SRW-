# #42 — 真正 Windows Native Host 模式的合成后端验收

`run_local.py --edition windows --workspace-lock host` **必须**验证：立即父进程拥有与 Core 完全一致的 schema-v2 `app.lock`、PID、端口、instance/session 和数据目录。只设置环境变量并直接启动嵌入式 Python 不能代表 WPF Host，会被正确拒绝为 `HOST_WORKSPACE_INVALID`。

旧 `verify_prepared_native.smoke_windows` 在临时数据目录直接启动上述命令，却没有代表 WPF Host 先获取工作区锁；这会在完整 Native ZIP 装配成功、13 模块导入成功后，报告 `embedded Windows backend exited before readiness`。此时**不应**移除 Core 安全校验、伪造 PID、使用真实工作区、修改原始 ZIP，或把“CLI 启动失败”误记为 GUI 失败。

## 修复与可核验事实

外部 Native 验收器从已经严格审计的**被测候选根目录**加载 `backend/srw/workspace_lease.py`，暂时禁止自身创建 `.pyc`，然后在临时合成数据目录由真实验收父进程获取 `WorkspaceLease(edition="windows", instance_id=…, session_id=…, port=…)`。父进程持续持有该锁，真实嵌入式 Python 子进程以原有 Host 模式启动，执行 HTTP ready/info 身份校验、请求正常停止；子进程退出后才释放锁。任意异常也不跳过租约释放，不暴露密钥、会话身份或原始 stderr。旧候选 ZIP 的源码和允许文件清单**完全不改**。

Linux 上新增真实父子 Python/Core/HTTP/临时 SQLite 集成验收，并验证异常退出/进程启动异常时租约释放和诊断脱敏。该测试通过不意味着 Windows Embedded Runtime 或实际 WPF GUI 已通过。原始 `c325e8e1dd8d` 候选的 Windows 13 导入成功事实仍保留；Windows 后端、GUI 与完整业务需要用户在新的干净候选解压目录使用**外置、经审计的新验收器**完成。

## 对旧 c325 候选的无损验收方式

使用独立的新版本验收源码、而不是覆盖旧候选内部 `scripts`；旧 ZIP 固定 SHA-256 为 `7a60e67e9dce873cb370b9eba0e30747080e9937d33a4fc848655f73ec457607`，其全部 2720 成员和来源在原验证器中保持严格校验。候选解压到一个**新的**独立文件夹；从外部运行 `py -3.12 -B scripts/verify_rebuilt_native.py --root <新目录> --zip <原候选.zip> --expected-zip-sha256 <固定哈希> --backend-smoke --evidence <新报告.json>`。第一次失败留下的解压目录、验收日志和候选 ZIP 均不删除、不覆盖、不篡改。

外置验收器的 SHA、来源、源清单和准确 CI 状态须另外核实。只有 Windows 上实际完成后端验收并输出独立 PASS 报告，才允许进行真实 WPF 双轮启动/退出验收。GUI 验收不代表 OCR/ASR/AI 和完整招聘闭环通过。
