# SRW 双载体试用版｜Q1R10（2026-11-13）

**预发布（Pre-release）／单用户本地试用（Early Pilot）／非 RC、非 GA。**

## 下载与安装

下载并完整解压 Release 的 `SRW_DualCarrier_Q1R10_Pilot_Release.zip`，依次双击 `01_INSTALL_SRW.cmd`、`02_START_SRW_EXE.cmd`。关闭桌面版后，可双击 `03_START_SRW_WEB.cmd`，在本机终端读取一次性配对码，在浏览器打开 `http://127.0.0.1:8765/v1` 配对。使用结束后在终端按 Ctrl+C，才可以重新打开 EXE。

- Windows 10/11 x64；原生 Host 需要 .NET 10 Desktop Runtime 和 Edge WebView2 Runtime。
- 包内包含嵌入式 Python、真实 SRW Core、Web 前端、五套 Knowledge 数据库；不需要另外安装 Python。
- 使用同一私有本地数据库 `%LOCALAPPDATA%\SRW\DualCarrierV0\data`，仅支持**轮流使用**两个入口，禁止并发独立 Core 双写；不要手工删除工作区锁。
- 首次试用只放合成/虚构招聘数据，勿放生产候选人资料或 Provider 密钥。

## 工件与来源身份

- 完整试用包：`SRW_DualCarrier_Q1R10_Pilot_Release.zip`
- 完整包 SHA-256：`b671b38db0595eb6b410d373e947f96f9a4478407ba20cfc53199a94bb0d0d7a`
- 完整包大小：102,277,338 字节
- 内嵌原始 Q1R10 Native ZIP：102,272,222 字节，2,812 个文件成员；SHA-256 `708b6deddaab5bda7a1d13c93a740e6aed3d4e6dfa3eebe1637f99fdb661cb1e`。原 ZIP 字节未改。
- Native 源码 SHA：`1d273b67bd0f571bd3c2e691e80a541c50e16f09`；VERSION `1.0.0-alpha10-convergence11`，Schema `v1_0014`。
- 后续启动器源码 PR [#259](https://github.com/ALV522/-SRW-/pull/259)，修复提交 `f9aa2d6ca0a0f97f8de814aec8e2f0cbfc33f499`；后续 main 的代码并不自动进入旧 Native ZIP。

发布时必须对真实 GitHub 下载资产重新执行 SHA-256 校验，不匹配即停止发布而不是改写这里的数字。GitHub 自动生成的 source code archives 不等于本 Windows 成品，使用上方完整 ZIP asset。

## 已得到的证据和使用边界

- Q1R10 原包静态哈希、ZIP CRC、Source 456/456、Runtime 2332/2332、Knowledge 5/5 校验通过；此前真实 Windows 四项 GUI 基础验收通过。
- B/C 在真实 Windows 1920×1200／135% 对**本地修正版启动器+原始 Q1R10** 验证 EXE 创建项目/已发布标准/候选人 → Web 同库配对并新增两条面试 → EXE 读回；工作区并发互斥、另一空工作区反序启动拒绝、正常退出和日志中配对码不泄漏均得到验证。详见 [#258 实机报告](https://github.com/ALV522/-SRW-/issues/258#issuecomment-6847066190)。
- 原始 PR #259 EXE 启动器曾有路径引号 P1 FAIL；B/C 已在真实 Windows 对修正版完整安装包进行 **6 次 Host 会话、安装后继续读写和 Web 占用时拒绝第二 Core** 验证（[18:58 报告](https://github.com/ALV522/-SRW-/issues/103#issuecomment-6850856228)），该 PASS 绑定 B/C 当时的 Windows ZIP SHA-256 feaad5217284c72db5d0de21927aee88ccb083427edbe01b686c065c46f6eec8，不能外推至未来不同字节包。
- 不支持两个独立后端同时运行；#230 跨实例 HMAC replay、#43 Supervisor/会话和 CAS、#124 Runtime/Knowledge 来源和许可、#130 物理恢复、#159 间歇退出问题仍未全部解决，因此**不得部署生产数据或标记稳定版**。

### 2026-11-13 跨平台 ZIP 哈希根因与修复

B/C Windows 外层 ZIP 与 A Linux 外层 ZIP 均为 102,277,338 字节，**7 个成员的大小、CRC32、解压后 SHA-256 全部一致**。唯一差异是 Python ZipInfo 默认的 ZIP 中央目录 “version made by” 的平台字节：Windows 为 0，POSIX 为 3。A 在 Linux 完整 ZIP 中仅把 7 个中央目录平台标识从 3 改为 0，重新计算的完整包哈希 **精确复现** B/C 的 feaad5217284c72db5d0de21927aee88ccb083427edbe01b686c065c46f6eec8。由此排除源码/数据库/启动器成员字节不一致。

装配脚本现在固定 info.create_system = 3；合成测试模拟 Windows 默认 0 并断言完整 ZIP 字节相同。Linux 运行修复后的真实 Q1R10 装配器仍得到 b671b38db0595eb6b410d373e947f96f9a4478407ba20cfc53199a94bb0d0d7a。B/C 需对**新 Git HEAD** 从零再装配，并确认 Windows 也得到 b671b38d...，再按来源/许可核验决定是否公开上传资产。本记录不表示已经创建 GitHub Release。

## 公开分发约束

用户已经授权将试用版本公开上传 GitHub。**发布者仍需核实第三方 Runtime 与五套 Knowledge 的来源、再分发许可及文件中无真实用户数据/密钥**，并留存脱敏的验证证据。只凭“用户允许使用公开仓库”不等于第三方数据库的版权/许可自动已获清除。若有不明来源或许可限制，改为仅发布启动器/源码与校验说明，完整 ZIP 不要挂为公开 asset。
