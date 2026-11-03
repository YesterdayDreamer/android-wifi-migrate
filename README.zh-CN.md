# WiFi Migrate

**跨品牌 Android Wi-Fi 迁移工具**

在 Windows 上整理、转换和迁移不同 Android 设备及品牌保存的 Wi-Fi 网络。

[English](README.md)

---

## 从这里开始：先试 WiFi Password Manager

**多数情况下，你可能根本用不到本项目。**

如果新旧两台 Android 手机都支持 [Shizuku](https://github.com/RikkaApps/Shizuku)，且 [WiFi Password Manager](https://github.com/Khh-vu/wifi-password-manager) 在两台设备上都能正常工作，直接用它导出和恢复已保存的 Wi-Fi 网络，通常最省事。

WiFi Password Manager 已经支持：

- 查看已保存的 Wi-Fi 网络和密码。
- 以 JSON 格式导入和导出配置。
- GZip 压缩和加密导出。
- 通过 Shizuku 或 Root 权限管理和恢复已保存网络。

**建议：** 安装 WiFi Migrate 前，先试试 WiFi Password Manager。

- [WiFi Password Manager · GitHub](https://github.com/Khh-vu/wifi-password-manager)
- [WiFi Password Manager · F-Droid](https://f-droid.org/packages/io.github.wifi_password_manager/)
- [Shizuku · GitHub](https://github.com/RikkaApps/Shizuku)

WiFi Password Manager 目前面向 Android 11 及更新版本。能否使用取决于设备、Android 版本和系统权限。

---

## 为什么需要 WiFi Migrate？

Android 没有一种适用于所有厂商和系统版本的已保存 Wi-Fi 配置迁移方式。

有些设备可以顺利使用基于 Shizuku 的工具，也有些设备调试选项有限，系统限制不同，或缺少方便的批量恢复方式。

**WiFi Migrate 将这些方法接入同一套 Windows 桌面流程。**

它补足现有工具在换机场景下的衔接环节，并继续利用 WiFi Password Manager 和 Android 已有的备份能力。

使用 WiFi Migrate，你可以：

- 从不同来源导入 Wi-Fi 数据。
- 整理和合并多份备份。
- 识别重复网络和凭据冲突。
- 选择要迁移的网络。
- 根据目标设备选择适合的迁移方式。
- 生成二维码和可打印的 PDF。
- 归档原始备份，供日后使用。

## 什么情况下适合使用？

| 你的情况 | 建议做法 |
|---|---|
| 两台手机都支持 Shizuku 和 WiFi Password Manager | 直接使用 WiFi Password Manager |
| 已有 WiFi Password Manager 备份 | 用 WiFi Migrate 打开，查看、整理和导出 |
| 旧机没有无线调试 | 尝试通过 USB ADB 启动 Shizuku |
| 旧机无法使用 Shizuku | 导入已有备份，或尝试受支持的传统备份方式 |
| 新机无法使用 WiFi Password Manager | 尝试 Android 导入助手或其他受支持的方式 |
| 只需迁移少量网络 | 生成二维码 |
| 想长期保存 Wi-Fi 备份 | 导出 JSON / CSV，并归档原始文件 |
| 想迁移 Windows 保存的网络 | 导入 Windows WLAN 配置 |

---

## 功能

### 1. 多种数据来源

支持从以下来源导入 Wi-Fi 配置：

- WiFi Password Manager 导出的 JSON。
- GZip 压缩的 JSON。
- 传统 Android ADB 备份（`.ab` / `.adb`）。
- TAR 归档和受支持的 Android 设置文件。
- Windows WLAN XML 文件。
- 已有的 CSV 和 JSON 文件。
- Windows 保存的 Wi-Fi 配置。

打开已有备份无需连接手机或安装 ADB。

### 2. 统一管理 Wi-Fi 数据

所有受支持的输入都会转换成统一的数据模型。

- 搜索、筛选和排序网络。
- 查看 SSID、密码、隐藏网络标记和认证类型。
- 检测重复条目。
- 识别名称相同、但密码或认证配置不同的网络。
- 合并多份备份，同时保留冲突信息。
- 选择单条网络或全部网络进行迁移。

扩展备份格式会尽量保留原始安全参数和源文件中其他可用的配置字段。

### 3. 多种迁移方式

根据目标手机的能力选择迁移方式。

| 方式 | 说明 | 状态 |
|---|---|---|
| **WiFi Password Manager** | 通过 Shizuku 和手机 App 导入网络 | 推荐 |
| **Android 导入助手** | 通过 Android 系统确认界面提交网络 | 实验性 |
| **ADB 直写迁移** | 通过 ADB 预览并尝试直接保存网络 | 实验性 |
| **二维码迁移** | 逐条扫描 Wi-Fi 配置二维码 | 可用 |

软件将来源设备和目标设备分开，并要求明确选择 ADB 设备，避免误操作另一台手机。

### 4. 导出与备份

支持以下输出：

| 格式 | 用途 |
|---|---|
| 扩展 JSON | 尽量保留原始配置数据 |
| WiFi Password Manager 兼容 JSON | 与 WiFi Password Manager 交换数据 |
| CSV | 便于查看和处理数据 |
| 二维码 PNG | 单个 Wi-Fi 网络的二维码 |
| 离线扫码清单 | 在本地浏览和核对二维码 |
| A4 PDF | 可打印的二维码合集 |
| 原始备份归档 | 保存源文件并使用 SHA-256 校验 |

**兼容性说明：** 导入 WiFi Password Manager 原生备份，与导入 WiFi Migrate 生成的 JSON，是两种不同操作。使用生成的 JSON 前，请先在目标 App 版本上验证。

二维码及部分迁移方式能表达的 Android Wi-Fi 配置有限。不支持的认证类型和高级设置可能会被跳过，或需要手动处理。

---

## 使用方法

### 第 1 步 · 从旧机获取 Wi-Fi 配置

推荐使用 WiFi Password Manager：

1. 在旧机安装 Shizuku 和 WiFi Password Manager。
2. 启动 Shizuku，并给 WiFi Password Manager 授权。
3. 在 App 内导出已保存的 Wi-Fi 网络。
4. 将导出的 JSON 或 GZip 文件传到 Windows 电脑。

如果没有无线调试，可以尝试通过 USB ADB 启动 Shizuku，具体取决于设备支持情况。

也可以直接打开已有备份，或尝试受支持的传统备份方式。

### 第 2 步 · 检查和整理

在 WiFi Migrate 中打开备份：

1. 查看解析出的网络。
2. 检查重复条目和冲突。
3. 按需合并其他备份。
4. 选择要迁移的网络。
5. 生成适合新机导入的数据。

### 第 3 步 · 迁移到新机

连接目标手机，选择可用的方式：

- WiFi Password Manager 导入。
- Android 导入助手。
- ADB 直写迁移。
- 扫描二维码。

某些方式需要在手机上授权或确认。

### 第 4 步 · 核对结果

WiFi Migrate 区分以下状态：

- 文件已传输。
- 配置已提交。
- 系统确认保存。
- 网络在系统已保存列表中可见。
- 已验证自动重连。

文件传输成功后，还需要确认网络是否保存。系统确认保存后，也需要单独验证自动重连。

---

## 使用要求

- Windows 桌面环境。
- 与项目依赖兼容的 Python 环境。
- 连接设备的操作需要 Android Debug Bridge（ADB）。
- 推荐的 App 迁移方式需要 Shizuku 和 WiFi Password Manager。

离线处理备份、生成二维码或 PDF 时，可以不用 ADB。软件会查找已有的 ADB，也能引导用户获取官方 Android Platform Tools。

安装详情见项目文档和发布说明。

---

## 兼容性与测试状态

下表记录的是实际设备测试结果。其他设备的兼容性仍需单独验证。

| 功能 | 当前验证情况 |
|---|---|
| HarmonyOS 4.2 → vivo X200 Ultra | 已实测 WiFi Password Manager 导出和导入成功 |
| 通过 USB ADB 启动 Shizuku | 已在华为设备上验证 |
| Android 导入助手 | 已在小米设备上验证安装、启动和文件传输，系统保存仍待验证 |
| ADB 直写迁移 | 已在华为和小米设备上验证只读预览，实际写入和自动重连仍待验证 |
| 二维码 / PDF | 已验证样例生成和二维码解码 |

实验性功能供测试使用，部分设备或固件版本可能无法使用。

---

## 隐私与安全

WiFi Migrate 在本地处理数据。

- 无需云端账号。
- Wi-Fi 数据在你的电脑本地处理。
- 原始备份文件可以单独归档。
- 迁移报告的设计会避开明文 Wi-Fi 密码。

**重要：** 导出的 JSON、CSV、二维码图片、PDF 和离线 HTML 页面可能含有明文凭据或可扫码获取的 Wi-Fi 信息。请按敏感文件保管，避免将个人备份上传到公开仓库。

---

## 鸣谢

- [WiFi Password Manager](https://github.com/Khh-vu/wifi-password-manager) · Android Wi-Fi 管理、备份与恢复。
- [Shizuku](https://github.com/RikkaApps/Shizuku) · 为 Android 应用提供访问特权 API 的途径。
- [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools) · Android 设备通信工具。

## 许可证

许可证信息见 [LICENSE](LICENSE)。
