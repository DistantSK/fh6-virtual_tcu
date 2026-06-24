# VirtualTCU 13.8.0 修改说明

本源码包基于上游 `fh6-virtual_tcu_evolution` 的 `v13.7.1` 代码修改，版本号已同步更新为 `13.8.0`。

## 新增功能

### F10 离合辅助开关

- 新增 `F10` 全局热键，用于快速开启或关闭离合辅助。
- 开关会同时同步 `feat_clutch_assist` 和 `vjoy_use_clutch`，避免键盘离合与 vJoy 离合状态不一致。
- 控制台会输出当前离合状态：`[Clutch] ON` 或 `[Clutch] OFF`。

### 悬浮窗离合状态显示

- Electron 悬浮窗新增 `CLUTCH ON/OFF` 状态显示。
- 经典、极简、赛车三种 HUD 模板都会显示当前离合辅助状态。
- 状态来自后端实时快照，切换后会同步到悬浮窗。

### 降档补油

- 新增降档补油功能，默认关闭。
- 新增配置项：
  - `feat_rev_blip`: 是否启用降档补油。
  - `blip_key`: 补油按键，默认 `w`。
  - `blip_ms`: 补油点按时长，范围 `0-150ms`，默认 `70ms`。
- 设置界面已加入降档补油开关、补油按键和补油时长设置。
- 当前补油时序为：降档键按下的同时快速点按油门，油门释放后再释放降档键。
- 如果离合辅助开启，时序为：踩离合，等待预压，降档键与油门几乎同时触发，释放油门，释放降档键，释放离合。

## 版本号

- 根 `package.json` 更新为 `13.8.0`。
- Electron、Dashboard、Shared、UI 子包版本同步为 `13.8.0`。
- Python 元数据 `pyproject.toml` 与 `virtual_tcu/__init__.py` 同步为 `13.8.0`。

## 验证

已执行以下检查：

```powershell
python -m pytest tests\test_clutch_assist.py tests\test_clutch_toggle_hotkey.py
python -m ruff check virtual_tcu\input\keyboard_output.py tests\test_clutch_assist.py
pyinstaller virtual_tcu.spec --noconfirm
pnpm.cmd --filter virtual-tcu package
```

结果：

- Python 单元测试通过。
- Ruff 检查通过。
- PyInstaller 后端构建通过。
- Electron 安装包构建通过。

## 打包说明

这是纯净源码包，不包含以下内容：

- `.git`
- `node_modules`
- Python/前端缓存目录
- PyInstaller `build` / `dist`
- Electron `apps/electron/release`
- 已生成的安装包和 zip 产物
- 本地运行配置文件 `tcu_config.json`

如需重新构建安装包，可按仓库说明安装依赖后执行：

```powershell
pnpm.cmd install --frozen-lockfile
pnpm.cmd build:dashboard
pyinstaller virtual_tcu.spec --noconfirm
pnpm.cmd --filter virtual-tcu package
```
