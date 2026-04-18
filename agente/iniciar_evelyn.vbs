Set oShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)

pyw = strDir & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pyw) Then
	pyw = fso.GetParentFolderName(strDir) & "\.venv\Scripts\pythonw.exe"
End If

' Inicia widget local da Evelyn
oShell.Run Chr(34) & pyw & Chr(34) & " " & Chr(34) & strDir & "\widget.py" & Chr(34), 0, False

' Inicia servidor web para acesso do celular
oShell.Run Chr(34) & pyw & Chr(34) & " " & Chr(34) & strDir & "\server.py" & Chr(34), 0, False
