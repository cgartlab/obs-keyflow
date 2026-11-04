' obs-keyflow —— 静默启动服务（无控制台窗口，可放进「启动」文件夹）
' 已有实例在运行时，新实例检测到健康探针会自行退出，不会重复挂钩子。
Option Explicit

Dim fso, sh, scriptDir, repoRoot, pyw, candidate, folder, pyRoot
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
repoRoot = fso.GetParentFolderName(scriptDir)
pyw = ""

' 1) %LOCALAPPDATA%\Programs\Python\Python3*\pythonw.exe
pyRoot = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python"
If fso.FolderExists(pyRoot) Then
    For Each folder In fso.GetFolder(pyRoot).SubFolders
        If LCase(Left(folder.Name, 6)) = "python" Then
            candidate = folder.Path & "\pythonw.exe"
            If fso.FileExists(candidate) Then pyw = candidate
        End If
    Next
End If

' 2) py 启动器的 pyw.exe
If pyw = "" Then
    candidate = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Launcher\pyw.exe"
    If fso.FileExists(candidate) Then pyw = candidate
End If

' 3) 交给 PATH
If pyw = "" Then pyw = "pythonw.exe"

sh.CurrentDirectory = repoRoot
sh.Run """" & pyw & """ -m keyflow", 0, False
