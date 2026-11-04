# obs-keyflow

> 在 OBS 录屏 / 直播画面上实时显示你正在按下的按键。Windows 本地运行，纯 Python 标准库，零第三方依赖。

![OBS 内实拍](assets/preview.png)

*上图为 OBS 场景实拍：底部一条玻璃胶囊显示最近按键，组合键合并为 `CTRL+C` 形式，按住中的键变白。*

**English** — A local keystroke overlay for OBS Studio on Windows. A low-level keyboard hook
streams key events over Server-Sent Events; OBS renders them with a built-in Browser source.
No OBS plugin, no version ABI coupling, no telemetry, no third-party packages.

---

## 特性

- **只显示最近按下的键**：底部紧凑一条，最新的最亮，越旧越淡；不按键时完全隐藏，不占画面
- **组合键合并**：`Ctrl+C` / `Ctrl+Shift+A`，`+` 号弱化显示；按住修饰键时同一枚键帽就地变成组合，不会多出一枚
- **按住高亮**：物理按住不放的键保持白色高亮
- **按键状态自愈**：每秒用 `GetAsyncKeyState` 校验收起的键是否还按着，丢失 keyup 也能自动纠正（切窗口、睡眠唤醒、远程桌面都不会卡住高亮）
- **单实例保护**：健康探针 + `SO_EXCLUSIVEADDRUSE`，重复启动（开机自启撞上手动启动）不会双钩子、不会抢端口
- **与 OBS 版本无关**：走浏览器源，不装任何插件，不受插件 ABI / OBS 升级影响
- **零第三方依赖**：仅 Python 标准库 + Win32 API
- **本地且最小暴露**：只监听 `127.0.0.1`，不联网、不落盘按键内容

## 快速开始

前置：**OBS Studio**（任意较新版本）＋ **Python 3.10+**。

```powershell
git clone <repo-url> obs-keyflow
cd obs-keyflow

# 1) 启动服务（前台可见日志；后台静默用 scripts\start.vbs）
python -m keyflow --console

# 2) 关闭 OBS 后，把浏览器源注入当前场景集合
python scripts/add-obs-source.py

# 3) 打开 OBS，场景里出现「按键显示」
```

可选：开机自动启动

```powershell
.\scripts\install-autostart.ps1      # 移除：.\scripts\install-autostart.ps1 -Remove
```

### 手动在 OBS 里加源

来源 → `+` → **浏览器** → 勾选**本地文件**关闭 → URL 填 `http://127.0.0.1:16900/`，
宽 `1920`、高 `1080`（与画布一致），勾选「关闭源时关闭页面」。

## 可调参数

改 OBS 源属性里的 URL 查询参数即可，改完点「刷新页面」：

| 参数 | 作用 | 默认 |
| --- | --- | --- |
| `?n=5` | 显示最近几个按键（组合键算 1 个） | 5 |
| `?size=64` | 键帽尺寸 px | 64 |
| `?gap=10` | 键帽间距 px | 10 |
| `?bottom=44` | 距画面底部距离 px | 44 |
| `?mode=full` | 切换成整块键盘样式 | recent |
| `?history=1` | 仅 `mode=full`：额外显示按键历史串 | 关闭 |
| `?debug=1` | 左上角显示连接状态点（绿=已连，红=断开） | 关闭 |

例：`http://127.0.0.1:16900/?n=6&size=72&bottom=56`

## 命令行

```
python -m keyflow [--host 127.0.0.1] [--port 16900] [--console]
                  [--no-hook] [--no-reconcile]
                  [--log <path>] [--log-level DEBUG]
                  [--version]
```

`--no-hook` 只起 HTTP 服务，便于在非 Windows 上调试页面；`--no-reconcile` 关闭自愈线程。

## 协议（供第三方叠加使用）

`GET /events` 为 SSE，每帧一个 JSON：

```json
{"t":"snap","pressed":["controlleft","a"]}      // 连接/校正时的全量快照
{"t":"key","k":"a","d":true}                     // d=true 按下, false 抬起
```

`GET /state` 返回同样的快照；`GET /healthz` 返回服务信息。键位 id 是稳定契约（`a`、`5`、
`enter`、`shiftleft`、`controlright`、`f5`、`numpad1`、`arrowup`、`volumeup` …）。

## 架构

```
keyflow/hook.py    WH_KEYBOARD_LL 钩子线程（消息泵 + 安装失败重试）
keyflow/keymap.py  vk/扫描码 → 稳定 key id（左右修饰键区分）
keyflow/hub.py     按下状态真相源：去重、自愈、广播（背压不阻塞钩子）
keyflow/server.py  HTTP：静态页面 + SSE + /state + /healthz
keyflow/__main__.py CLI、日志轮转、单实例探测、优雅退出
web/index.html     叠加画面（最近按键 / 整块键盘两种模式）
scripts/           start.vbs 静默启动、add-obs-source.py 注入源、开关机自启、关闭 OBS
```

数据流：`键盘 → hook → hub → SSE → 浏览器源渲染`。钩子线程只做解析与入队，
渲染完全在 CEF 里，钩子不会被慢客户端拖住。

## 稳定性设计：把潜在问题逐条堵住

| 潜在问题 | 对策 |
| --- | --- |
| 钩子安装失败（句柄截断等） | 所有 Win32 调用显式声明 `argtypes/restype`；安装失败每 5s 重试，服务不退出 |
| 丢失 keyup → 键帽卡住变白 | 每秒 `GetAsyncKeyState` 校验收起的键，物理松开即释放 |
| 键盘自动重复刷屏 | `Hub.key_down` 对已按下的键直接忽略 |
| 慢客户端拖住钩子 | 每客户端有界队列，满了丢事件而不是阻塞 |
| 重复启动（开机自启 + 手动） | 先探测 `/healthz`，再 `SO_EXCLUSIVEADDRUSE` 绑定，第二实例直接退出 |
| 端口被 TIME_WAIT 占用 | 绑定失败退避重试 6 次，日志写明原因 |
| 日志无限增长 | `RotatingFileHandler`，512 KB × 3 |
| OBS 或服务重启 | EventSource 自动重连；连上先收 `snap` 全量校正 |
| 断线期间残留高亮 | 连接错误时清空本地状态；另有 8s 兜底释放 |
| 浏览器源报错白页 | 页面由服务提供；服务未启动时源为空白而非白页 |
| 目录穿越 | 静态文件限定在 `web/` 内，越界返回 403 |
| 线程异常导致钩子被摘 | 钩子回调内 try/except，异常不冒出回调 |
| 组件崩溃带崩全局 | 钩子/自愈/服务线程独立，任一失败记录日志后自恢复 |

## 为什么不写成 OBS 插件

本项目最初尝试了社区主流的 **input-overlay** 原生插件，结论是**装上就报插件加载失败**：

- 该插件 5.1.3 是针对 OBS 33 编译的，导入了 `gs_image_file_ex_init` /
  `gs_image_file_ex_init_texture` / `gs_image_file_ex_free`
- OBS 32.0.2 的 `obs.dll` 里没有这些符号 → `LoadLibrary` 返回错误码 127，模块加载失败
- OBS 32 只要发现第三方模块加载失败，启动就会弹「插件加载失败」

改用浏览器源后：不需要任何插件、不受 OBS 版本升级影响、崩溃面也更小。

## 已知限制

- **仅 Windows**（依赖 `WH_KEYBOARD_LL` / `GetAsyncKeyState`）
- **管理员权限窗口里的按键收不到**：Windows UIPI 不允许低完整性进程的钩子读取高完整性窗口输入。
  需要覆盖时，服务和 OBS 都要以管理员身份运行。
- **全局钩子会看到所有窗口的按键**：录制时如需输入密码等敏感内容，请先隐藏该源或结束服务。
- 需要服务常驻（已提供开机自启）。

更多问题见 [docs/troubleshooting.md](docs/troubleshooting.md)。

## 开发

```powershell
python -m unittest discover -s tests -t . -v      # 23 项单元/集成测试，无第三方依赖

# 可选：安装成命令
pip install -e .
keyflow --console
```

目录约定：`keyflow/` 只放服务端逻辑，`web/` 只放渲染层，两者通过 `id + SSE` 协议解耦；
`scripts/` 放一次性运维脚本（注入源、开关自启、关闭 OBS）。

## 卸载

1. `.\scripts\install-autostart.ps1 -Remove`（移除开机启动）
2. 结束 `pythonw.exe` 进程
3. OBS 里删除「按键显示」源
4. 删除仓库目录；日志在 `%LOCALAPPDATA%\obs-keyflow\`

## 许可

[MIT](LICENSE) © 2026 CGArtLab
