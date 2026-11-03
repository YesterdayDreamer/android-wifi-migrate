# 命令行使用

安装后 `wifi-migrate` 与 `python launch.py` 的参数一致。下面的设备 ID 均为占位文字，需要换成自己明确选择且已授权的设备。

```bash
# 查看帮助；交互菜单；桌面入口
python launch.py --help
python launch.py wizard
python launch.py gui

# 本地检查与转换（不操作手机）
python launch.py inspect examples/synthetic-settings.xml
python launch.py convert examples/synthetic-settings.xml --out runs/demo
python launch.py convert /path/to/phone.adb --out runs/from-backup
python launch.py convert /path/to/windows-xml-directory --out runs/from-windows-xml
```

加密 `.adb` 需要密码时会交互询问，不接受命令行明文密码参数。输出目录必须不存在，避免覆盖已有结果。不要在公开 Issue 中粘贴解密密码。

```bash
# 明确指定 ADB 路径也可用环境变量 ADB_PATH
python launch.py devices --adb /path/to/adb
python launch.py probe --serial DEVICE_ID --adb /path/to/adb

# 默认尝试只备份设置提供程序，并自动检查、转换内容
python launch.py backup --serial OLD_DEVICE_ID --out runs/old-phone --adb /path/to/adb

# 仅在确实需要复现原流程时选择全量模式，可能备份其他应用和共享存储
python launch.py backup --serial OLD_DEVICE_ID --legacy-full --out runs/full-backup --adb /path/to/adb

# 复制二维码到新机专用图片目录，不自动扫码，不删除照片
python launch.py push-qr runs/demo --serial NEW_DEVICE_ID --adb /path/to/adb

# 默认只预览，不写手机
python launch.py import-adb runs/demo/networks.json --serial NEW_DEVICE_ID --adb /path/to/adb

# 明确添加或更新前一条配置；可能更新目标机同名网络
python launch.py import-adb runs/demo/networks.json --serial NEW_DEVICE_ID --adb /path/to/adb --apply --limit 1

# 确认系统列表确实保存了试存条目后，再批量处理
python launch.py import-adb runs/demo/networks.json --serial NEW_DEVICE_ID --adb /path/to/adb --apply --resume --confirm-trial

# Windows 本机：显式读取已保存网络，并检查 XML 是否真的含明文密钥
python launch.py export-windows --out runs/windows
```

ADB 保存默认使用基本字段。隐藏网络、禁用自动加入等参数只有目标机帮助中可确认时才使用；支持不明则跳过。同名同类型的冲突密钥不会自动决定哪条覆盖哪条。原始 64 位十六进制 PSK、不受支持的安全类型和某些 WEP 配置会跳过，源数据仍保留。

`--resume` 依据特定设备和记录指纹恢复，且会先读回网络列表。批量保存需要同一输入文件、目标和范围的试存记录，并且试存条目当前仍可见。单条试存可用 `--apply --trial`。若限定范围（例如 `--limit 10`），试存和批量时都传相同范围。系统列表可见不验证密钥或联网。

退出码：`0` 表示检查/转换完成，或 ADB 保存条目均收到确认且在列表可见；`1` 表示文件、依赖、权限或步骤错误；`2` 表示 ADB 保存中存在失败、跳过或未确认条目。即使保存退出码为 `0`，也未验证密码和联网。
