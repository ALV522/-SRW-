# SRW HTML 网站探索 — E1/E2/E3/E4/E5 Windows 演示说明

这些都是 **真实 C11 后端 + 一次性合成数据** 的源码演示，不需要已有 C11 Windows EXE；也不是 Windows Native Portable 正式包。

## 获取完整 ZIP

1. 打开[已全部通过的 SRW HTML E1–E5 CI（运行 39189966339）](https://github.com/ALV522/-SRW-/actions/runs/39189966339)，或进入 [Sandbox 工作流](https://github.com/ALV522/-SRW-/actions/workflows/html-site-sandbox.yml)选择更新的 Success 运行。
2. 在该运行的 **Artifacts** 中[直接打开已验证 ZIP 下载入口](https://github.com/ALV522/-SRW-/actions/runs/39189966339/artifacts/12160145418)，其名称以 `SRW-HTML-E1-E5-WINDOWS-SOURCE-DEMO-` 开头的 ZIP（需要有私有仓库访问权限的 GitHub 账号）。
3. 解压**整个 ZIP**，不要只下载或复制某个 CMD 文件。文件夹顶层应该有：

```text
START_HERE.cmd       # E1：真实 API，只读网页
START_E2.cmd         # E2：合成数据，代理层乐观并发实验
START_E3.cmd         # E3：合成数据，SQLite 原子事务实验
START_E4.cmd         # E4：一个 Core，两个浏览器载体实验
START_E5.cmd         # E5：Core 连接身份校验与独立附着凭据
PACKAGE_README.md
PACKAGE_MANIFEST.sha256.json
requirements-ci.txt
backend/
frontend/
browser_acceptance/
convergence_tests/
explorations/
```

4. 本机需要 **Python 3.12**，第一次启动需联网安装指定依赖到当前演示文件夹的 `.e1-demo-venv`，不会安装到正式 SRW，也不会打开实际招聘数据库。无需当前的 C11 Windows EXE。

## 四个可运行入口

| 入口 | 允许写入什么 | 主要验证 |
|---|---|---|
| `START_HERE.cmd` | Web 只读 | 真实 C11 API、项目、候选人、材料、工作空间 |
| `START_E2.cmd` | 仅本次合成候选人的跟进计划 | 代理层 ETag、过期写入返回 412 |
| `START_E3.cmd` | 仅本次合成候选人的跟进计划 | ETag 比较、业务修改和审计同一 SQLite 事务 |
| `START_E4.cmd` | 仅本次合成候选人的跟进计划 | 独立 Core + 两个浏览器入口，关闭其中一个不影响另一端 |
| `START_E5.cmd` | 仅本次合成候选人的跟进计划 | 两个载体需先验证独立连接凭据；未授权与错误 Core 拒绝访问 |

**E4/E5 所谓的 Desktop surrogate 只是第二个浏览器服务入口，并非 WPF/WinUI/Native EXE。E5 的一次性连接链接不可分享；此实验不包含正式用户登录与远程访问授权。**

双击对应的顶层 CMD。E1 页面顶部应显示 `LIVE · web · GET-only`；E3/E4 的网页顶部应显示 `LIVE · web · E3 atomic synthetic`。如果只显示 MOCK，不算真实 API 验收成功。

## 推荐体验顺序

先打开 E1，依次查看工作台、项目列表、候选人目录、独立候选人工作空间。E2 可用两个浏览器标签验证第一个写入成功、第二个旧版本写入被拒绝。E3 同样可以验证冲突，但版本比较与审计在实验 Core 的 SQLite 事务中完成。E4 启动后会显示两个不同的本机 URL，两者共享同一临时 C11 Core；在其中一个界面保存合成 Action Plan，然后在另一个界面点击刷新，应能看见同样的状态。

关闭某个浏览器标签不应立即关闭另一个；**Core 由 CMD 中的临时控制器持有**。停止演示时在 CMD 窗口按 `Ctrl+C`，它会停止后端并尝试清除一次性 SQLite 和 Knowledge 文件。

Windows 上 SQLite 文件有时会短暂被系统进程占用；演示启动器现在会有界重试清理。如果最终仍报告清理失败，先确保相关演示 Python 进程已经退出，再按报错指向的**临时目录**清理。不要清理或重命名正式 SRW 的 `data` 目录。

## 当前不包含的能力

- 尚无通过 Native WPF/WebView2 实机验收的 C11 EXE；
- E3 的事务代码和版本表仍为独立实验，未迁移到正式主线；
- E4 并非 Windows Service、系统托盘或正式进程主管理程序；
- 没有正式生产 Knowledge DB、真实候选人、实时 AI/OCR/ASR Provider 验收；
- 未实现跨电脑同步与远程授权，也不对局域网开放端口。

未来 Web + EXE 的目标仍是**一个 Core / 同一业务权威状态 / 两种 UI 载体**，而不是两个 SQLite 数据库之间的自动双向同步。

## 如果出现错误

请反馈 `START_HERE/E2/E3/E4` 中哪个入口失败，以及报错信息（隐藏个人目录、用户名及敏感信息）。无需上传真实简历、数据库、API Key、锁文件或完整候选人日志。

除非你希望亲自评估 UI，当前继续开发和 CI 验收都不要求你进行操作。

## E5 附着验证（合成数据，可选）

在完整 ZIP 顶层双击 `START_E5.cmd`，控制器为两个网页载体各分配一个不同的、120 秒内仅能兑换一次的附着链接。网页兑换后会跳转到不含令牌的地址，并通过 HttpOnly Cookie 持续访问本次模拟 Core。未附着的其他浏览器、错误载体的链接、已经兑换的旧链接以及身份不符的 Core 应被拒绝。

E5 仍然**不是生产认证系统**。不要把它当作多人联网服务，不要复制附着链接给他人。关闭演示窗口并用 Ctrl+C 结束控制器即可销毁临时数据。
