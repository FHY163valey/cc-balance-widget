[CmdletBinding()]
param([string]$Directory = [Environment]::GetFolderPath('Desktop'))
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $Directory 'CC Balance Widget.lnk'
if (Test-Path -LiteralPath $target) { throw "Shortcut already exists: $target. Remove or rename it explicitly first." }
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($target)
$link.TargetPath = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
$link.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $root 'Start.ps1') + '" -ShowErrors'
$link.WorkingDirectory = $root
$link.Description = 'CC Balance Widget'
$link.IconLocation = "$env:WINDIR\System32\shell32.dll,20"
$link.Save()
Write-Output $target
