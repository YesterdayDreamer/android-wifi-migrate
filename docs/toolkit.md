# WiFi Migrate 0.3

## 第一次打开

WiFi Password Manager 路线需要在手机安装 [Shizuku](https://github.com/RikkaApps/Shizuku/releases) 和 [WiFi Password Manager](https://github.com/Khh-vu/wifi-password-manager/releases)。连接并授权 USB 调试后，在对应旧机或新机页面点「USB 启动 Shizuku」。桌面按该机当前安装位置启动服务，再到手机打开 WiFi Password Manager 并确认授权。若找不到启动文件，可打开手机 Shizuku 的电脑启动页，使用当前版本显示的命令。

迁移方式直接显示在「迁移与结果」页。若唯一在线的手机仍被标为旧机，换接新机或在来源页清除旧机选择，然后在目标页重新查找。助手路线依次安装 APK、复制 JSON、打开助手。实际要保存 WiFi 时，在手机的 Download 中选该文件，再确认系统对话框。

1. **只有备份文件**：在首页打开备份。可离线检查、合并其他未加密文件、按选择导出、生成 PDF 或保存原件。
2. **旧手机还在**：进入迁移，找到来源设备。若手机端工具可用，在旧机确认 Shizuku 授权并导出。可以打开电脑上的备份，或用「从旧机取回导出文件」读取旧机 Download 里的 JSON/GZip。没有 App 路线时可尝试旧式备份。
3. **要迁到新手机**：在检查页选全部或部分，进入迁移页。扫码时可跳过连接。批量迁移时用独立的新机选择框查找并检测设备。推荐优先使用检测到的 WPM + Shizuku，其次尝试系统确认助手，有二维码时可扫码。「电脑直连（高级）」也是独立标签页。
4. **检查结果**：文件复制仅显示等待手机操作。WPM 请核对 On-device；App-only 是应用内部记录。助手在手机上保存结果 JSON，再将报告传回电脑，用「读入结果」验证同一批导入文件。ADB 直连展示命令返回和列表回读。用户可以单独记录自己确认的系统列表或重连条数。

ADB 会优先使用已保存路径或项目附近的工具，再查用户缓存、PATH 和常见 SDK 位置。找不到时可以「选择本地 ADB」或「从 Google 下载」。下载有进度并可取消，解压与 adb version 校验完成后保存到 Windows 用户目录 `%LOCALAPPDATA%\AndroidWiFiBackupToolkit\tools\platform-tools`。使用官方包应遵守 [Google 下载条款](https://developer.android.com/tools/releases/platform-tools#downloads)。

## 故障排查

- 电脑直连属于实验性功能。桌面先预览，再试存一条。系统已保存列表回读成功并由用户再次核对后，才允许批量保存。无法回读时请选择其他路线。
- 原生 WPM 明文 JSON 可直接在手机 App 导入。工作台转换出来的兼容 JSON 尚未真机验证。Open/OWE 过渡条目不会用开放认证提交。WPA2/WPA3 过渡条目在通用扫码、助手和电脑直连中只使用明确标记的 WPA2 兼容项。
- 0.3.0 新版助手报告校验输入 SHA-256、总数、处理数、逐条 ID 和批次。仍可导入旧报告，但也必须匹配来源和条数。报告不能代替系统列表和重连检查。

- 下载失败可重新尝试，或选择已有完整 Platform Tools 目录中的 adb.exe。离线备份和导出不依赖 ADB。
- 显示待授权时请在对应手机确认调试弹窗。两台手机同时连接时分别选择角色。
- 检测到 Shizuku 服务后，仍需在 WiFi Password Manager 内检查授权。
- 找不到手机系统保存界面时可切换扫码。助手报告和当前结果不匹配时，请回到生成该 JSON 的那次导出。
- 每次迁移结果写入结果目录的 migration-results.json。文件没有明文密钥，但可能含设备标识。普通错误日志只记录错误类型。

## 审计与设计

首版已有 Tk 工作台、命令行、ADB 连接及试存、流式 Android Backup 解包、旧表格与 Windows XML 输入、PNG 与离线扫码清单。主要缺口是附加配置只留在原件、结果难以筛选、没有归档入口、没有公开 API 导入助手。沿用 Python、Tk、现有记录和输出流程。扩展记录和来源适配器与界面分开。

| 模块 | 用途 |
| --- | --- |
| archive / formats / core | 容器与格式识别、原始安全参数及 Wi-Fi / IP / 企业配置、统一记录 |
| outputs / pdf | 主 JSON、CSV、兼容 App JSON、二维码、离线清单及选定条目 PDF |
| catalog / catalog_ui | 搜索、列排序、同名筛选、查看单条密码、选择记录导出 |
| vault | 原件副本、历史目录、字节大小、时间、来源名称、结果关联与 SHA-256 |
| adb / workflow | 设备、只读能力检查、备份、导入文件传输与实验性保存 |
| android-importer | 免 Shizuku 系统确认式导入，使用明文 WiFi Password Manager JSON |

主 JSON 的 raw 字段可能包含企业网络敏感数据。迁移派生文件只使用各目标格式能表达的字段。源里缺少的常见字段在 missing_fields 标记，兼容输出仍沿用既有默认值。选择保留哪些同名条目后可另存一份结果。原备份始终保留。

## 选择路线

1. **两台手机都支持 WiFi Password Manager**。旧机启动 Shizuku，在 App 内授权并导出。PC 可打开明文 JSON 或 GZip JSON，检查后输出兼容 JSON。直接使用原导出也可以。新机启动 Shizuku，在 App 内导入并保存到系统。项目的“复制导入 JSON 到手机”可把结果放进所选设备的 Download 目录。
2. **旧机只能通过 USB 或手头已有备份**。在 Shizuku 里复制当前版本展示的 USB 启动命令，在电脑用 adb -s 指定设备执行。若 Shizuku 无法使用，尝试工作台的定向备份或选取已有 ADB/TAR/settings.data。是否能得到配置取决于旧机。将结果交给路线 1、免 Shizuku 助手或扫码。
3. **分享、打印或手动迁移**。在结果页打开“检查 / 导出 / PDF”，搜索并选择需要的网络，生成 A4 多列 PDF 并自动打开。安装可选依赖 python -m pip install -e ".[pdf]"。CSV、PNG 和离线扫码清单仍自动生成。二维码只携带可表达的 SSID、安全类型、密钥、隐藏标记。

WiFi Password Manager 使用项目源码定义的 JSON 数组、可选 GZip 和加密包装。当前支持普通 JSON 与 GZip JSON 输入，兼容输出为明文 JSON。没有承诺版本间的稳定格式规范。加密导出请在原 App 解密后重新导出。未复制第三方实现。用户实测 HarmonyOS 4.2 经 USB ADB 启动 Shizuku，vivo X200 Ultra 经无线调试启动，已完成两端导出与导入。该结果以用户报告记录。

桌面 doctor 只确认 ADB 已授权、Shizuku 应用及进程可见性、当前无线调试设置和系统命令声明。App 是否获授权、是否能读凭据、是否能写入系统仍分别验证。自研 Shizuku 读取与恢复依赖厂商隐藏 Binder API，当前复用现有 App，避免维护两套隐藏接口适配。

## 免 Shizuku 助手

桌面优先使用 **迁移到新手机 → 免 Shizuku · 电脑直连**。通过 USB 授权新机后，先检测和预览，试存首条可用且无冲突的记录，再按需批量保存。换设备或更改迁移范围后需要重新检测。固件支持 ADB 保存时，整个流程可从电脑完成。下面的手机助手适用于希望改走 Android 官方系统确认接口的用户，该接口需从手机应用发起。

使用 JDK 17、Gradle 8.9 和 Android SDK 35。在仓库根目录运行 gradle -p android-importer assembleDebug，APK 在 android-importer/app/build/outputs/apk/debug/。也可用 Android Studio 打开 android-importer。安装后在手机内选择 wifi-password-manager.json，每批至多五条，由系统确认，助手按系统返回码汇报。没有联网权限，输入文件经系统文件选择器授予读取权限。

支持 Android 11+ 的常见个人网络、隐藏网络及开放网络。纯 SAE 和纯 OWE 依赖目标设备支持，过渡组合在助手中按 WPA2 或开放兼容项提交。跳过 WEP、企业认证、同名冲突和需要额外网络策略的条目；保留原始数据供其他路线处理。系统设置入口可能被厂商省略。系统返回成功后，检查系统已保存列表，再关开 Wi-Fi 核对自动重连。

真机验证使用临时虚构测试网络。检查单条保存、拒绝后重试、已有网络、同名冲突及权限受限固件。再分别测旧机 USB Shizuku 运行、未授权、App 导出；新机无线启动、App 导入、系统保存及重连。ADB 命令探测、Shizuku 进程可见与实际保存成功分别记录。

## 原件与发布

在结果页选“归档原文件”，或执行 python launch.py archive 原文件 --result 结果目录。历史存于 runs/archives，按时间排列。用 python launch.py verify-archive 归档目录 核对后，可复制其中的 original 文件或直接将其重新选作输入。文件归档、结果文件夹和 PDF 都包含敏感数据。

Windows 保留 Start.cmd。PyInstaller 可从 launch.py 打包 Tk 工作台，需带上 qrcode、PyPNG、Crypto 和可选 ReportLab 字体资源，并在干净 Windows 环境验证。ADB 作为外部 Platform Tools 由用户选择。当前发布以 Python 源码包和单独的 Android 构建为主。
