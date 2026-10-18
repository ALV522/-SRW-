# SRW Web / EXE 共用数据：E1 Windows 试运行

此文档只针对独立探索分支 `explore/html-site-prototype`。**不会修改 SRW EXE、数据库或主线源码。**

## 本次测试的目标

让浏览器中的 SRW Web E1 页面连接到**已经运行的 Windows SRW EXE 所启动的同一个后端**。

这轮仅开放 GET 只读操作。Web 不能添加/修改候选人、Claim、评价、Offer，也不能启动 OCR、ASR、AI 任务。

## 前置条件

- 需要一套**当前 API 兼容**的 SRW 本地服务：至少包含 `/api/v1/info`、`/api/v1/runtime/info`、`/api/v1/dashboard` 和 Candidate Workspace 等 E1 API。
- 你已启动该版本的 Windows EXE，并且它启动了后端服务。
- Windows 环境有可信任的 Python 3。用 `py -3 --version` 或 `python --version` 检查即可。E1 使用 Python 标准库，不需要 pip。
- 不要把历史 `v0.8.x` Windows 包自动视为 C11 API 兼容版本。若端点不兼容，先不要碰历史数据库，也不要尝试升级旧数据库。

**实际限制：GitHub 当前 C11 主线并未完成官方 Windows Native 可执行包的实机验收。若手头只有历史 EXE，本次的“同一 EXE 实例”互通测试可能暂时无法运行；这不影响继续进行 E1 的合成 API 测试。**

## 第一步：取得探索目录

1. 打开私有仓库的 `explore/html-site-prototype` 分支。
2. 使用 GitHub 的 **Code → Download ZIP** 下载该分支，并解压到独立目录。**不要覆盖任何 SRW Portable / EXE 工作目录**。
3. 找到 `explorations/html-site`，其中包含 `run_e1_windows.cmd`、`serve_e1.py` 和 `e1-live.html`。

## 第二步：确认 EXE 的 data 目录

在 EXE 仍运行时，定位它的用户数据目录。默认是完整 Windows 应用根目录中的 `data`，如果 EXE 用 `--data-root` 指定了自定义目录，则使用该自定义目录。

里面应当能看到：

```text
data/
  app.lock/
    instance.json
```

这个文件由 Windows Host 写入，包含动态端口、版本与实例身份。

**不要把 `instance.json` 的完整内容发到聊天或上传到公共仓库。** 它包含本机路径和会话/实例标识。程序只需要在本机读取即可。

## 第三步：启动只读 Web 页面

最简单的方式：

1. 保持 EXE 打开。
2. 将上述 `data` 文件夹拖到 `run_e1_windows.cmd` 上，或双击 BAT 后粘贴 `data` 文件夹的完整路径。
3. 脚本先读取 `instance.json`，然后验证运行中的 SRW 实例、会话、版本以及数据目录身份。
4. 验证通过之后会在本机选择空闲端口并自动打开浏览器。

如果你想手动执行：

```powershell
py -3 serve_e1.py --data-root "C:\Path\To\SRW\data" --port 0 --open-browser
```

切勿在测试时启动另一个 SRW 后端去争夺相同数据库的锁。

## 如何判断成功

浏览器右上角应该看到：

```text
LIVE · windows · GET-only
```

然后进入“招聘项目”并打开一个项目，再打开某位候选人的工作空间。阅读并比较项目状态、候选人阶段、Source、Claim、Criterion 等信息。

如果显示：

```text
MOCK · API unavailable
```

这**不算测试通过**，说明 E1 没有成功使用真实数据库。首页会显示连接失败的原因。

如果页面打开失败，命令行应显示具体错误。常见原因是：
- EXE 没有运行或没有写入 `app.lock/instance.json`；
- `data` 路径错误；
- 旧 EXE API 不兼容；
- SRW 实例身份/会话不匹配（脚本拒绝连接）；
- Python 不存在；
- 后端尚未启动完成。

## 如果只有 Web 服务，没有兼容 EXE

手动指定已经运行的 SRW local HTTP 服务地址：

```powershell
py -3 serve_e1.py --upstream http://127.0.0.1:8000 --port 0 --open-browser
```

端口 `8000` 仅作为示例，实际以服务启动输出为准。这个模式会核查 SRW 产品身份，但没有 EXE lock，因此不能单凭它证明存在双载体的 Windows EXE。

## 结束测试

直接在探索脚本的命令行窗口按 `Ctrl+C`。

这只停止只读 Bridge；不会关闭 EXE，也不会替你操作或删除生产数据。

## 最后告诉我什么

测试后只需要回报：

1. 右上角显示 `LIVE` 还是 `MOCK`；
2. 如果失败，复制终端中的**错误类型和文字**，可以隐去用户名、完整文件路径与敏感数据；
3. 如果成功，告诉我“项目列表和候选人工作空间能否看到与 EXE 一致的数据”。

**不需要上传简历、候选人名单、数据库、API Key、完整锁文件或原始日志。**

如果你目前没有可运行的 C11 Windows EXE，直接告诉我这一点即可。届时继续验证 Web 单载体的真实 C11 服务，而不会要求你用旧数据库冒险升级。
