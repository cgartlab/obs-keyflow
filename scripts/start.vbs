' obs-keyflow - silent launcher (no console window). Put it in the Startup folder.
' English-only comments on purpose: Windows Script Host reads .vbs as ANSI and
' non-ASCII comments can break parsing on some locales.
' If an instance is already running, the new one exits on its own (health probe).
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

' 2) py launcher's pyw.exe
If pyw = "" Then
    candidate = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Launcher\pyw.exe"
    If fso.FileExists(candidate) Then pyw = candidate
End If

' 3) fall back to PATH
If pyw = "" Then pyw = "pythonw.exe"

sh.CurrentDirectory = repoRoot
sh.Run """" & pyw & """ -m keyflow", 0, False
