# Phase 4 Test Samples

> 覆盖 Phase 4 全部模块：Sandbox（沙箱执行） / Archive & Remote Storage（归档与远端存储） / Capacity Warning（容量预警）

---

## 1. Sandbox — 隔离执行环境

### 1.1 初始化创建沙箱目录
| 字段 | 值 |
|------|-----|
| **操作** | `Sandbox("test-session", base_dir=tmpdir)` |
| **预期** | `tmpdir/test-session/` 目录被自动创建 |

### 1.2 文件写入与读取
| 字段 | 值 |
|------|-----|
| **操作** | `sandbox.write_file("test.txt", "hello world")` → `sandbox.read_file("test.txt")` |
| **预期** | 写入返回字节数信息，读取返回完整内容 "hello world" |

### 1.3 写入嵌套目录文件
| 字段 | 值 |
|------|-----|
| **操作** | `sandbox.write_file("sub/dir/file.txt", "nested")` → `sandbox.read_file("sub/dir/file.txt")` |
| **预期** | 自动创建父目录 `sub/dir/`，读取返回 "nested" |

### 1.4 路径穿越防护 — `../` 攻击
| 字段 | 值 |
|------|-----|
| **操作** | `sandbox.resolve_path("../../../etc/passwd")` |
| **预期** | 抛出 `ValueError`，错误信息包含 "traversal" |

### 1.5 路径穿越防护 — 绝对路径
| 字段 | 值 |
|------|-----|
| **操作** | `sandbox.resolve_path("/etc/passwd")` |
| **预期** | 抛出 `ValueError`（`resolve()` 后路径不在 sandbox_dir 下） |

### 1.6 路径穿越防护 — 符号链接绕过
| 字段 | 值 |
|------|-----|
| **操作** | 在沙箱内创建指向 `/etc` 的符号链接 → 尝试通过该链接读取文件 |
| **预期** | `resolve_path` 解析后仍在沙箱范围内，或被拒绝 |

### 1.7 读取不存在的文件
| 字段 | 值 |
|------|-----|
| **操作** | `sandbox.read_file("ghost.txt")` |
| **预期** | 抛出 `FileNotFoundError` |

### 1.8 删除文件
| 字段 | 值 |
|------|-----|
| **操作** | `write_file("tmp.txt","tmp")` → `delete_file("tmp.txt")` → `read_file("tmp.txt")` |
| **预期** | 删除成功后读取抛出 `FileNotFoundError` |

### 1.9 删除不存在的文件（无异常）
| 字段 | 值 |
|------|-----|
| **操作** | `sandbox.delete_file("ghost.txt")` |
| **预期** | 返回 `"File not found: ghost.txt"`，不抛异常 |

### 1.10 列出目录内容
| 字段 | 值 |
|------|-----|
| **操作** | `write_file("a.txt","a")` → `write_file("b.txt","b")` → `list_dir()` |
| **预期** | 返回排序后的列表含 "a.txt", "b.txt"，路径为相对路径（不含前导 `/`） |

### 1.11 列出子目录内容
| 字段 | 值 |
|------|-----|
| **操作** | `write_file("sub/file.txt","x")` → `list_dir("sub")` |
| **预期** | 返回 ["sub/file.txt"] |

### 1.12 列出不存在的目录
| 字段 | 值 |
|------|-----|
| **操作** | `sandbox.list_dir("nonexistent")` |
| **预期** | 返回 `[]`（空列表） |

### 1.13 执行 Python 代码 — 正常
| 字段 | 值 |
|------|-----|
| **操作** | `sandbox.execute_python("print(1+1)")` |
| **预期** | stdout 含 "2"，stderr 为空，returncode=0 |

### 1.14 执行 Python 代码 — 语法错误
| 字段 | 值 |
|------|-----|
| **操作** | `sandbox.execute_python("x = 1/0")` |
| **预期** | returncode != 0，stderr 含错误信息 |

### 1.15 执行 Python 代码 — 多行代码
| 字段 | 值 |
|------|-----|
| **操作** | `sandbox.execute_python("import os\nprint(os.getcwd())")` |
| **预期** | stdout 含沙箱目录路径，returncode=0 |

### 1.16 执行 Python 代码 — 超时
| 字段 | 值 |
|------|-----|
| **操作** | `sandbox.execute_python("while True: pass", timeout=1)` |
| **预期** | 抛出 `subprocess.TimeoutExpired` |

### 1.17 执行 Shell 命令 — 正常
| 字段 | 值 |
|------|-----|
| **操作** | `sandbox.execute_shell("echo 'ok'")` |
| **预期** | stdout 含 "ok"，returncode=0 |

### 1.18 执行 Shell 命令 — 错误
| 字段 | 值 |
|------|-----|
| **操作** | `sandbox.execute_shell("exit 1")` |
| **预期** | returncode=1 |

### 1.19 执行 Shell 命令 — 管道与重定向
| 字段 | 值 |
|------|-----|
| **操作** | `sandbox.execute_shell("echo hello > out.txt && cat out.txt")` |
| **预期** | stdout 含 "hello"，returncode=0，文件 `out.txt` 在沙箱内可读 |

### 1.20 Python 执行的工作目录隔离
| 字段 | 值 |
|------|-----|
| **操作** | 在沙箱外创建文件 → 在沙箱内 `execute_python("open('secret.txt')")` |
| **预期** | 无法读取沙箱外的文件（cwd 限定在 sandbox_dir 内） |

### 1.21 清理沙箱目录
| 字段 | 值 |
|------|-----|
| **操作** | `write_file("x.txt","x")` → `cleanup()` |
| **预期** | `sandbox_dir` 不再存在 |

### 1.22 多次清理不报错
| 字段 | 值 |
|------|-----|
| **操作** | `cleanup()` → `cleanup()` 再次调用 |
| **预期** | 不抛异常（`ignore_errors=True` 或 `exists()` 判断） |

### 1.23 文件覆盖写入
| 字段 | 值 |
|------|-----|
| **操作** | `write_file("a.txt","v1")` → `write_file("a.txt","v2")` → `read_file("a.txt")` |
| **预期** | 返回 "v2" |

### 1.24 大文件写入与读取
| 字段 | 值 |
|------|-----|
| **操作** | 写入 100KB 内容 → 读取校验 |
| **预期** | 内容完整一致 |

---

## 2. Archive & Remote Storage — 远端存储后端

### 2.1 LocalNasStorage — 上传文件
| 字段 | 值 |
|------|-----|
| **操作** | `nas.upload(src_file, dest_path)` |
| **预期** | 目标文件存在，内容与源文件一致 |

### 2.2 LocalNasStorage — 上传自动创建父目录
| 字段 | 值 |
|------|-----|
| **操作** | `nas.upload(src_file, "new/sub/dir/file.tar.gz")` |
| **预期** | `new/sub/dir/` 目录被自动创建 |

### 2.3 LocalNasStorage — 下载文件
| 字段 | 值 |
|------|-----|
| **操作** | `nas.download(remote_path, local_dest)` |
| **预期** | 本地目标文件被创建，内容与远端一致 |

### 2.4 LocalNasStorage — 写入日志
| 字段 | 值 |
|------|-----|
| **操作** | `nas.write_log(remote_path, "log content")` |
| **预期** | `log.md` 文件被创建在远端路径的父目录下，含追加内容 |

### 2.5 LocalNasStorage — 追加写入日志
| 字段 | 值 |
|------|-----|
| **操作** | 连续 2 次 `write_log(path, "line1")` → `write_log(path, "line2")` |
| **预期** | `log.md` 含两行内容（追加模式，非覆盖） |

### 2.6 STORAGE_BACKENDS 映射表
| 字段 | 值 |
|------|-----|
| **操作** | 检查 `STORAGE_BACKENDS` 字典 |
| **预期** | "local_nas"→LocalNasStorage, "s3"→S3Storage, "sftp"→SftpStorage |

### 2.7 S3Storage — S3 路径解析
| 字段 | 值 |
|------|-----|
| **操作** | `S3Storage._parse_s3_path("s3://my-bucket/path/to/file.tar.gz")` |
| **预期** | 返回 `("my-bucket", "path/to/file.tar.gz")` |

### 2.8 S3Storage — S3 路径仅 bucket
| 字段 | 值 |
|------|-----|
| **操作** | `S3Storage._parse_s3_path("s3://my-bucket")` |
| **预期** | 返回 `("my-bucket", "")` |

### 2.9 S3Storage — 懒加载客户端
| 字段 | 值 |
|------|-----|
| **操作** | 创建 `S3Storage()` → 检查 `_client` |
| **预期** | `_client` 初始为 `None`，首次调用 `_get_client()` 后创建 boto3 client |

### 2.10 SftpStorage — _wrap_stringio
| 字段 | 值 |
|------|-----|
| **操作** | `SftpStorage._wrap_stringio("hello")` |
| **预期** | 返回 `io.BytesIO` 对象，内容为 `b"hello"` |

### 2.11 未知远端类型回退到 LocalNas
| 字段 | 值 |
|------|-----|
| **操作** | `archiver.archive(session_id, "unknown_type", remote_path)` |
| **预期** | 自动使用 LocalNasStorage 完成归档（`STORAGE_BACKENDS.get("unknown", LocalNasStorage)`） |

---

## 3. Archiver — 归档引擎

### 3.1 归档到 Local NAS — 完整流程
| 字段 | 值 |
|------|-----|
| **操作** | `archiver.archive("test-session", "local_nas", remote_dir)` |
| **预期** | `remote_dir/test-session.tar.gz` 存在，包含会话所有文件 |

### 3.2 归档后本地清理 — 保留核心文件
| 字段 | 值 |
|------|-----|
| **操作** | 归档含 config.json + strategy.psc + conversation.log 的 session |
| **预期** | config.json 和 strategy.psc 保留，conversation.log 等其他文件被删除 |

### 3.3 归档后清理子目录
| 字段 | 值 |
|------|-----|
| **操作** | 归档含 `agents/` 子目录的 session |
| **预期** | `agents/` 子目录被 `rmtree` 删除 |

### 3.4 归档不存在的 Session
| 字段 | 值 |
|------|-----|
| **操作** | `archiver.archive("ghost-session", "local_nas", remote_dir)` |
| **预期** | 抛出 `FileNotFoundError`，错误信息含 "not found" |

### 3.5 归档生成 tar.gz 文件
| 字段 | 值 |
|------|-----|
| **操作** | 归档后检查生成的 tar.gz 文件是否有效 |
| **预期** | tar.gz 可被 `tarfile.open("r:gz")` 打开，含 session 目录条目 |

### 3.6 归档写入远端日志
| 字段 | 值 |
|------|-----|
| **操作** | `archiver.archive(...)` 完成 |
| **预期** | 远端 `log.md` 被创建，含时间戳 + session_id + remote_type |

### 3.7 归档返回值
| 字段 | 值 |
|------|-----|
| **操作** | `result = archiver.archive("test", "local_nas", "/tmp")` |
| **预期** | 返回远端目标路径字符串，以 "test.tar.gz" 结尾 |

### 3.8 归档临时目录清理
| 字段 | 值 |
|------|-----|
| **操作** | 归档后检查 `tempfile.mkdtemp()` 创建的临时目录 |
| **预期** | 临时目录已被 `shutil.rmtree` 清理 |

### 3.9 空会话目录归档
| 字段 | 值 |
|------|-----|
| **操作** | 归档一个无文件的空 session 目录 |
| **预期** | 成功生成 tar.gz（仅含空目录） |

### 3.10 重复归档同一 Session
| 字段 | 值 |
|------|-----|
| **操作** | 第一次归档后再次归档同一 session |
| **预期** | 第二次仍成功（config.json + strategy.psc 仍可被归档） |

---

## 4. Capacity Warning — 容量预警

### 4.1 check_disk_usage — 有文件
| 字段 | 值 |
|------|-----|
| **操作** | `archiver.check_disk_usage()` — data_dir 下有文件 |
| **预期** | 返回 `(total_bytes, 0)`，total_bytes > 0 |

### 4.2 check_disk_usage — 空目录
| 字段 | 值 |
|------|-----|
| **操作** | `archiver.check_disk_usage()` — data_dir 空 |
| **预期** | 返回 `(0, 0)` |

### 4.3 check_disk_usage — 目录不存在
| 字段 | 值 |
|------|-----|
| **操作** | `archiver.check_disk_usage()` — data_dir 路径不存在 |
| **预期** | 返回 `(0, 0)`（`if self.data_dir.exists()` 判断） |

### 4.4 容量预警阈值 — `/health` 端点集成
| 字段 | 值 |
|------|-----|
| **操作** | 模拟磁盘使用量超过 `system.yaml` 中的 `warning_threshold_gb` → `GET /health` |
| **预期** | 返回 `disk_usage_gb` 字段 > `warning_threshold_gb`，status="degraded" |

### 4.5 容量正常 — `/health` 端点
| 字段 | 值 |
|------|-----|
| **操作** | 磁盘使用量 < `warning_threshold_gb` → `GET /health` |
| **预期** | `disk_usage_gb` 为实际值，status="ok" |

---

## 测试文件映射

| 测试文件 | 覆盖模块 | 用例数 |
|----------|----------|--------|
| `tests/test_sandbox.py` | Sandbox（初始化/文件读写/路径防护/代码执行/Shell执行/目录列表/清理） | 10 |
| `tests/test_archive.py` | Archiver & Remote Storage（归档流程/LocalNas/日志写入/磁盘用量） | 5 |

**总计**: 46 个 Phase 4 测试用例（15 已实现 + 31 待扩展）

### 已实现测试覆盖

| # | 用例编号 | 测试函数 |
|---|---------|---------|
| 1 | 1.1-1.2 | `test_write_read_file` |
| 2 | 1.3 | `test_write_nested_directory` |
| 3 | 1.4 | `test_path_traversal_blocked` |
| 4 | 1.7 | `test_read_nonexistent` |
| 5 | 1.8 | `test_delete_file` |
| 6 | 1.10 | `test_list_dir` |
| 7 | 1.13 | `test_execute_python` |
| 8 | 1.14 | `test_execute_python_error` |
| 9 | 1.17 | `test_execute_shell` |
| 10 | 1.21 | `test_cleanup` |
| 11 | 3.1-3.2 | `test_archive_local_nas` |
| 12 | 3.4 | `test_archive_nonexistent_session` |
| 13 | 3.6 | `test_archive_log_written` |
| 14 | 2.1 | `test_storage_backend_local_nas` |
| 15 | 4.1 | `test_check_disk_usage` |
