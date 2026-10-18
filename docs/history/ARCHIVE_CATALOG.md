# 过去的开发包：原始 ZIP 档案目录

本页记录 2026-10-18 用户重新提供的四份历史开发包；**不是**对这些包的验收、背书，也不代表这些包已经上传到 GitHub。精确文件名、大小、SHA-256 和版本定位以 [机器可读清单](LEGACY_ARCHIVES.json) 为准。

| 档案 ID | 历史版本（文件名自述） | 类型 | 压缩体积 | ZIP 成员 | 状态 |
|---|---|---|---:|---:|---|
| `legacy-0810-source` | v0.8.10 | 源码 + Knowledge 快照 | 45,427,080 B | 856 | 仅登记 |
| `legacy-0810-windows-assembler` | v0.8.10 | Windows 装配器 + 嵌套 Overlay ZIP | 44,960,321 B | 6 | 仅登记 |
| `legacy-0812-r2-source` | v0.8.12-R2 | Truth Closure 源码 + Knowledge 快照 | 46,177,312 B | 887 | 仅登记 |
| `legacy-alpha10-web-portable` | v1.0-alpha10 | 历史 Web Portable，包含 Python Runtime | 76,697,890 B | 1,710 | 仅登记 |

**SHA-256（完整原始字节）**

- v0.8.10 Source：`25bb54bc10fe3022b4f3dae9d6f7c598e9e960fc262884c4948130d097f130f6`
- v0.8.10 Windows Assembler：`7d468a21572a8e353ce082238840eec5f9848e494c0be799e6e101c633d4694b`
- v0.8.12-R2 Source：`80b3b2d68de23c04d9e5a62d9701d716ee89d4ea71f7041c34d728fb1e267fb3`
- v1.0-alpha10 Web Portable：`92deadadc861673fd762a8453cc0877ff21a16f5e1ea12e6172fdb2b1e6929d4`

## 档案与主线的关系

- v0.8.10 源码：成熟业务能力、Knowledge 和 Windows 装配架构的历史参考，不等于当前 Git 主线。
- v0.8.10 Assembler：独立的旧装配工具链。不是最终 Windows Portable 安装包；其中还封装另一个 ZIP。
- v0.8.12-R2：当前 Convergence 的**能力完整性参照**，不用于覆盖 `main`。
- alpha10 Web Portable：用于追溯产品化和招聘流程思路，与后续 Convergence 的业务逻辑不是完全等价的版本。不能依据“Portable”文件名断定 Windows WPF 原生 GUI 已验证。

在文件目录层面检查到上述三个非装配器包内带有大型 Knowledge DB，历史 alpha10 包还带可执行 Python Runtime；这些字节从未通过本轮安全／许可证／个人信息内容审查。ZIP 结构检查、SHA-256 计算只能证明文件没损坏并方便日后识别，**不能证明其安全、无候选人隐私、来源可信或可运行**。装配器的内层 ZIP 同样需要在独立检查后才可使用。

## 上传到 GitHub 的操作与结果

已检查连接权限和支持的操作。仓库为 Private，但 **Private 不等于自动完成个人信息与密钥审计**。当前连接可以写源码和提交 PR，却没有创建 GitHub Release 附件并上传大型二进制文件的接口。使用普通 Git 对这些 43–73 MiB 的压缩包直接提交将膨胀仓库并绕过独立的工件发布管理，因此**本轮没有上传四份二进制 ZIP**；只登记本目录和 SHA 清单。

以后若 Release asset 上传渠道可用，可创建 **非正式发行版** `Historical Development Packages (Unverified)`，逐项完成来源核验、数据库敏感信息检查、嵌套包与可执行文件检查，之后附上上述 SHA 与明确标注的历史版本说明，切勿使用正式版本号或 Windows 已验收标签。

## 本地复核命令

将四份原始 ZIP 放入同一目录，并使用原始文件名：

```bash
python scripts/audit_legacy_archives.py --catalog docs/history/LEGACY_ARCHIVES.json --directory /path/to/historical-zips
```

工具只打开 ZIP 文件目录并计算 ZIP 整体 SHA，不解压、不执行内嵌程序；失败返回 exit code 2。无论报告是否通过，其 `safe_to_publish` 永远为 `false`，内容审查另行开展。
