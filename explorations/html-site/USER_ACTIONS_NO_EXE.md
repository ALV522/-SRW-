# 没有 C11 Windows EXE 时，如何体验真实 SRW Web

目前不需要 Windows EXE。本探索区已经包含一个可以启动**真正 C11 API + 一次性 SQLite + 合成招聘数据**的 Windows 源码演示程序。

它不是正式 Windows 发布包，也不会对你的正式数据库进行升级或迁移。

## 操作

1. 打开私有仓库的 `explore/html-site-prototype` 分支，在 **Code → Download ZIP** 下载整个分支并解压到单独目录。
2. 检查本机有 **Python 3.12** 和网络连接。首次启动需要下载本项目锁定版本的 Python 依赖，安装在该探索目录自己的 `.e1-demo-venv`，而不是系统 Python。
3. 打开 `explorations/html-site/run_e1_demo_windows.cmd`，等待网页自动打开。

成功时，网页右上角显示：

```text
LIVE · web · GET-only
```

可以进入“招聘项目”查看自动生成的合成招聘项目、候选人及原始文本材料，也可以进入“候选人”体验跨项目筛选和独立工作空间。

**注意：不会读取任何正式候选人数据。** 演示数据在 Windows 临时目录中创建，并在按 `Ctrl+C` 停止后销毁。

若显示 `MOCK`，该网页没有连上真实 C11 服务，不计为本次体验成功。

## 如果暂时没有 Python 3.12

不需要立刻安装。探索项目的 Windows CI 已经在隔离测试环境中运行了同一源码启动器，工程推进不以你的电脑具备运行环境为前提。

## 可提供的反馈

如果你愿意体验，只需告诉我：

- 网页是否显示 `LIVE · web · GET-only`；
- “工作台、招聘项目、候选人工作空间”的导航是否清晰；
- 是否有具体步骤过于繁琐或某个控件无法操作；
- 若失败，给出脱敏后的错误描述即可。

无需上传数据库、候选人资料、API Key、Windows Host 锁文件或完整本地日志。

## 区分两个不同验收

### 已自动验证：不需要 EXE 的真实 Web 运行

`run_e1_demo.py` 使用真实 C11 后端、SQLAlchemy/SQLite 和最小 Knowledge Fixture。独立测试不仅调用接口，还在 Chromium 中点击和检查页面，并在 Windows CI 中执行源码 Demo 冒烟测试。

### 尚未验证：真正的 EXE + Browser 互通

后续有可运行、API 兼容的 C11 Windows Native 包后，才使用 `run_e1_windows.cmd` 附着在 EXE 当前的数据目录及动态端口上，做真实双 Carrier 测试。

**不要用历史 0.8.x EXE 强行连接新的 E1 接口，也不要拿历史真实数据库执行源代码演示。**

## 未来产品化方向

最终将维护共同业务 Core，再同时发布：
- 浏览器 Web Edition；
- Windows EXE Edition（共享相同 Web UI 和后端 API 契约）。

同一台电脑上的 Web + EXE 连接一个 Core，自然信息互通。跨电脑/跨网络的共享需另行构建身份认证、服务端部署及权限模型。不要把它和“两个离线数据库自动双向同步”混为一谈。
