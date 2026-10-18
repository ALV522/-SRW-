> **历史文档**：本文件只描述 C09 恢复范围，不应取代 [当前 README](README.md)、[主线治理](docs/REPOSITORY_GOVERNANCE.md) 或 [当前开发状态](DEVELOPMENT_STATE.md)。

# Convergence 09 source scope

Contains backend/frontend and desktop Host source, Convergence recovery tests, synthetic Knowledge fixtures, release/verification tools and documentation. SOURCE_MANIFEST.sha256 covers current tracked files; SOURCE_RECOVERY_MANIFEST.sha256 is the preserved 212-file C08 historical inventory.

Does not contain embedded runtime, production Knowledge databases, candidate materials or a certified Windows Native binary. CI creates a deterministic source ZIP and SHA-256 sidecar bound to the exact commit. See docs/RELEASE_PROCESS.md for promotion and rollback.
