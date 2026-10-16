# SRW Convergence 08

- Version: `1.0.0-alpha10-convergence08`
- Capability baseline: **v0.8.12-R2**
- Schema: `v1_0014`（本轮无数据库迁移）

本轮继续按“0.8.x 功能完整性优先”推进：恢复 PDF Claim 图形化高亮定位、扩大 Knowledge Controlled Apply 到 competency alias、补回备份/CSV 安全 gate，并恢复**完整项目包导出/Preview/摘要锁定导入**。项目包携带项目业务状态与材料 Blob，导入时全部业务 ID 重映射；历史 Decision Context 保持 historical，必须在新项目上下文重新评价。

Windows WPF/WebView2 Host ABI 继续保持兼容；缺少精确 v0.8.8 carrier 时不伪造原生 EXE。

启动 Web/Host-ready 版本：`START.bat`。Windows 原生重组入口：`BUILD_WINDOWS_NATIVE.bat`。
