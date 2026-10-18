# SRW Web / EXE 双载体探索：没有 EXE 时如何试用

**优先下载 Actions 的完整、自动验收过的演示 ZIP。不要单独下载某个 .cmd 文件。**

## 现在应当下载哪个文件

1. 打开探索分支的最新成功运行：
   https://github.com/ALV522/-SRW-/actions/workflows/html-site-sandbox.yml
2. 选择结论为 **Success** 且含有 `Publish verified E1 source demo` 任务的运行。
3. 在运行页面最下方的 **Artifacts** 下载名称以
   `SRW-E1-REAL-CORE-WINDOWS-SOURCE-DEMO-` 开头的 ZIP。
4. **解压整个 ZIP** 到新目录，目录顶层应当存在：

```text
START_HERE.cmd
START_E2.cmd
PACKAGE_README.md
PACKAGE_MANIFEST.sha256.json
requirements-ci.txt
backend/
frontend/
browser_acceptance/
convergence_tests/
explorations/
```

如果没有这些文件，说明下载或解压不完整。不要只下载
`run_e1_demo_windows.cmd`，它不是独立的启动程序。

## E1：真实后端，只读 Web 演示

双击顶层的 **START_HERE.cmd**。

- 本机需要 Python 3.12（`py -3.12` 或 `python`）。
- 首次运行需要联网下载锁定的 Python 依赖；
- 依赖安装在解压目录自己的 `explorations/html-site/.e1-demo-venv`；
- 会启动真实 C11 SRW 后端及浏览器 HTML UI；
- **全部招聘项目、候选人、简历文本都是合成数据**，在系统临时目录中保存；
- E1 Browser 对后台只有 GET 权限，不能修改数据；
- 命令行窗口中按 Ctrl+C 退出，并终止临时服务和删除测试数据。

浏览器右上角成功标志是：

```text
LIVE · web · GET-only
```

这说明 E1 使用真实 SRW API，而不是网页内置的 Mock。

## E2：真实后端、两个浏览器的受控写入实验（可选）

双击顶层的 **START_E2.cmd**。

E2 同样使用单独的一次性 SQLite 数据库。打开网站左侧的
`E2 受控写入`，选择合成候选人并加载其跟进计划：

1. 在浏览器里复制一个标签页，确保两个标签页都读取了初始版本；
2. 第一个标签页编辑负责人，点击“条件保存（If-Match）”；
3. 第二个标签页在不刷新的情况下编辑负责人并保存；
4. 第二个标签页应收到 `412 STALE_ACTION_PLAN`；
5. 重新读取最新版本以后，第二个标签页才可以再次保存。

E2 **只允许写入演示程序本轮创建的合成候选人 Action Plan**。
其它业务 API 仍只读；它不连接真实 EXE，也不接触任何正式招聘数据。
当前版本冲突检查位于独立探索代理层，**不等同于正式后端的数据库级原子并发控制**。

## 与正式 Windows EXE 的关系

这两个入口都**不需要**已有 C11 Windows EXE，不应被当作已经发布的
Windows Portable / WPF Native 产品。未来真正的 Web/EXE 双载体会连接一个
共同的 SRW Core，保留 OCR、ASR、Knowledge、Evidence、Audit 和人工决策边界。

## 如果启动失败

- `ERROR: INCOMPLETE SRW E1 SOURCE PACKAGE`：ZIP 没有完整解压，
  或从目录中单独搬走了 CMD。应从完整的顶层 `START_HERE.cmd` 启动。
- `Python 3.12 is required`：安装 Python 3.12 或使用支持的版本命令；
  脚本不会修改系统 Python。
- 依赖安装失败：检查联网情况，不要自行混装其它 Python 库。
- `LIVE` 未显示：查看窗口内错误，告诉我脱敏后的错误文字。

你只需反馈 E1/E2 是否能启动、网页是否显示 `LIVE`、是否存在按钮或业务交互故障。
**不要发送真实简历、SQLite 数据库、Key、完整锁文件或包含个人数据的日志。**
