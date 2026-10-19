# 开发与构建

普通用户使用 Releases 的完整便携包。以下步骤面向构建源码的开发者。源码构建不需要运行游戏；真正生成字幕补丁时需要玩家自己的受支持游戏资源。

## 环境

- Windows 64 位、Python 3.14（已验证，含 Tkinter）。
- JDK 17+ 用于编译 Java 字体辅助程序。发行包只需 JRE 17。
- JPEXS 26.3.0：从官方 https://github.com/jindrapetrik/jpexs-decompiler/releases/tag/version26.3.0 获取，解压到 `.tools/ffdec/`，其中应有 `ffdec.jar` 和 `lib/`。
- Temurin JRE 17：从 https://github.com/adoptium/temurin17-binaries/releases 获取 Windows x64 JRE，解压到 `.tools/jre/<版本>/bin/java.exe`。已验证版本为 17.0.20.1+1。
- `fonts/` 已包含 OFL 字体与来源说明，不需要游戏字体。字体辅助程序自身源码位于 `runtime/EmbedLearningFont.java`。

运行时目录应保留上游完整 license/legal 文件。项目通过单独进程运行 JPEXS；字体辅助程序在运行时链接外置 FFDec 库，JAR 可以替换为接口兼容版本。

## 编译与启动

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
javac --release 17 -cp ".tools/ffdec/ffdec.jar;.tools/ffdec/lib/*" -d runtime runtime/EmbedLearningFont.java
.\.venv\Scripts\python.exe configurator_app.py
```

如果 javac 不在 PATH，请使用 JDK 的 javac.exe 完整路径。禁止将 JDK/JRE、下载缓存或游戏导出资源提交到仓库。

## 便携包

```powershell
.\.venv\Scripts\python.exe package_tool.py
```

输出 `dist/MilesLanguageTool/` 与 ZIP。打包器按允许列表复制源码，排除游戏 GFX/SWF、本地化资源和游戏索引。发行包保留全部第三方许可证与项目许可。

## 验证随包运行时

```powershell
.\dist\MilesLanguageTool\MilesLanguageTool.exe --self-test C:\Temp\miles-runtime-check.json --game C:\Games\MilesMorales
```

该自检会在报告旁生成本地字体编译探针，不会安装探针。测试报告目录可能含从本地游戏读取的脚本，请留在本机。

## LGPL 库替换与重链接

字体辅助程序的源码及编译命令均公开。替换 `.tools/ffdec/lib/ffdec_lib.jar` 或便携包 `runtime/ffdec/lib/ffdec_lib.jar` 等外置兼容库后，可以重新编译辅助程序、重新打包。项目的非商业许可不重新许可或限制第三方库本身；第三方库修改、调试和再分发适用其自身条款。
