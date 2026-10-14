Option Explicit
Dim fso, shell, bat, rc
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
bat = fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), "KAMPUS_GAME_ARENA_KILIT_V5.bat")
rc = shell.Run("cmd.exe /d /c """ & bat & """", 0, True)
WScript.Quit rc
