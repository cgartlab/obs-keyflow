# obs-keyflow 故障排查

先看日志：`%LOCALAPPDATA%\obs-keyflow\logs\keyflow.log`（自动轮转，512 KB × 3）。

## 画面上什么都没有

| 检查 | 做法 |
| --- | --- |
| 服务是否在跑 | 浏览器打开 <http://127.0.0.1:16900/healthz>，应返回 `{"service":"obs-keyflow",...}` |
| 端口是否被占 | `Get-NetTCPConnection -LocalPort 16900 -State Listen` |
| 源是否可见 | OBS 里「按键显示」源左侧眼睛图标是否打开，图层是否在最上层 |
| 页面是否连接 | 源属性里 URL 后加 `?debug=1`，画面左上角出现绿点=已连上，红点=没连上 |
| 是否按键被吞 | 在记事本里敲几个键，看是否出现 |

**服务没运行时，源会显示为空白**（页面由服务提供），不会出现报错白页。

## OBS 里没有「按键显示」源

场景集合被重置/切换过。关闭 OBS 后重新注入：

```powershell
python scripts/add-obs-source.py
```

加 `--scene "场景名"` 指定其他场景，`--dry-run` 只预览。

## 弹出「插件加载失败」

obs-keyflow 不使用任何 OBS 插件，出现这个提示说明是**别的插件**在报错：

1. 看 OBS 日志 `%APPDATA%\obs-studio\logs\` 里 `not loaded` / `failed to open` 那一行，路径就是罪魁
2. 常见原因是插件为其他 OBS 版本编译（例如 input-overlay 5.x 需要 OBS 33，而 OBS 32 会失败）
3. 删掉该路径下的插件文件夹即可，OBS 启动就不再提示

本仓库曾试过原生插件方案，结论记录在 README「为什么不写成 OBS 插件」。

## 某些按键不显示

- **管理员权限窗口里的按键**：非管理员进程的键盘钩子收不到更高完整性级别的输入（Windows UIPI 限制）。
  需要覆盖这些窗口时，服务与 OBS 都要以管理员身份运行。
- **游戏全屏独占 + 反作弊**：部分游戏会屏蔽全局钩子；改用无边框窗口模式通常可解。
- **输入法组合过程**：物理按键仍会上屏，显示的是按下的物理键，而不是上屏汉字。

## 组合键显示不对

`Ctrl+C` 显示成两枚键帽，通常是旧版页面缓存。选中源 → 属性 → 点「刷新页面（不使用缓存）」。

## 开机后不自动启动

```powershell
.\scripts\install-autostart.ps1     # 重新安装
```

或检查 `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\obs-keyflow.lnk` 是否存在。

## 端口 16900 冲突

改端口启动：`python -m keyflow --port 17000`，并把 OBS 源的 URL 改成新端口。
（默认端口写死在 URL 里，换端口后需同步改源属性。）

## 日志里出现「自愈: 释放 N 个残留按键」

这是正常保护：说明有一次按键抬起事件丢失，服务根据物理键状态自动纠正。频繁出现时检查是否在用远程桌面 / 切换用户 / 睡眠唤醒。
