Add-Type -AssemblyName PresentationFramework
$message = "缺少 Python / Python is missing.`n`n请从官网安装 Python（最低 3.10），启用 Tcl/Tk and IDLE。安装完成后重新打开启动器。`nInstall Python with Tcl/Tk, then relaunch.`n`nhttps://www.python.org/downloads/windows/`n`n现在打开下载页面？ / Open download page?"
$result = [System.Windows.MessageBox]::Show($message, 'Typecraft', 'YesNo', 'Warning')
if ($result -eq 'Yes') { Start-Process 'https://www.python.org/downloads/windows/' }
