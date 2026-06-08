# 公司电脑部署

## 安装位置

将整个 `chinese-data-dsl` 文件夹复制到目标电脑的 Codex skills 目录：

```powershell
$target = Join-Path $env:USERPROFILE ".codex\skills\chinese-data-dsl"
New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
Copy-Item -Recurse -Force "D:\path\to\chinese-data-dsl" $target
```

如果公司统一设置了 `CODEX_HOME`，放到：

```powershell
%CODEX_HOME%\skills\chinese-data-dsl
```

## Python 依赖

在目标电脑使用实际运行 Codex/脚本的 Python 安装依赖：

```powershell
python -m pip install --user -r "$env:USERPROFILE\.codex\skills\chinese-data-dsl\requirements.txt"
```

需要系统级或虚拟环境部署时，去掉 `--user`，改在管理员批准的 Python 环境中安装。

## 离线部署

在可联网电脑预下载 wheels：

```powershell
python -m pip download -r .\requirements.txt -d .\wheels
```

将 skill 文件夹和 `wheels` 一起复制到目标电脑，然后安装：

```powershell
python -m pip install --no-index --find-links .\wheels -r .\requirements.txt
```

## 验证

进入 skill 目录后运行：

```powershell
python -m unittest discover -s tests
python .\scripts\zhdata.py .\references\example_pandas.zd --emit-python
python .\scripts\zhdata.py .\references\example_numpy.zd --emit-python
```

如果要实际执行示例，建议先复制 `references\example_*.zd` 和 `references\demo_data.csv` 到临时目录，避免在 skill 目录内留下业务输出文件。

## 打包建议

分发前排除这些临时文件：

- `__pycache__`
- `.pytest_cache`
- `.mypy_cache`
- `references\city_sales.csv`
- `references\matrix.npy`
- 本地虚拟环境目录，例如 `.venv`

所有 `.md`、`.zd`、`.csv`、`.py` 文件保持 UTF-8 编码。
