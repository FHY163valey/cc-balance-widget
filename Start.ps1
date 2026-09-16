[CmdletBinding()]
param([switch]$Demo, [switch]$Check, [switch]$DependenciesOnly, [switch]$ShowErrors)
$ErrorActionPreference = 'Stop'
trap {
    if ($ShowErrors) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            $_.Exception.Message, 'CC Balance Widget startup failed') | Out-Null
    } else {
        Write-Error $_ -ErrorAction Continue
    }
    exit 1
}

$candidates = @()
$venv = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venv) { $candidates += $venv }
foreach ($name in @('python.exe', 'py.exe')) {
    $found = Get-Command $name -ErrorAction SilentlyContinue
    if ($found) { $candidates += $found.Source }
}
$python = $null
foreach ($candidate in ($candidates | Select-Object -Unique)) {
    try {
        $output = & $candidate -c 'import sys, tkinter; assert sys.version_info >= (3,12); print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $output -and (Test-Path -LiteralPath "$output")) {
            $python = "$output"
            break
        }
    } catch { }
}
if (-not $python) {
    throw 'Python 3.12+ with Tkinter was not found. Install Python with Tcl/Tk, or create .venv in this project.'
}
if (-not $Demo) {
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    if (-not $node) {
        $standard = Join-Path $env:ProgramFiles 'nodejs\node.exe'
        if (Test-Path -LiteralPath $standard) {
            $env:PATH = "$(Split-Path -Parent $standard);$env:PATH"
            $node = Get-Command node.exe
        }
    }
    if (-not $node) { throw 'Node.js 22+ is required. Install Node.js and reopen PowerShell.' }
    $major = & $node.Source -p 'Number(process.versions.node.split(/[.]/)[0])'
    if ($LASTEXITCODE -ne 0 -or [int]$major -lt 22) { throw 'Node.js 22 or newer is required.' }
}
if ($DependenciesOnly) {
    Write-Output 'Dependencies OK'
    exit 0
}
$entry = Join-Path $PSScriptRoot 'run.py'
$options = @()
if ($Demo) { $options += '--demo' }
if ($Check) {
    & $python $entry @options --check
    exit $LASTEXITCODE
}
$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) { throw 'pythonw.exe is missing from the selected Python installation.' }
$arguments = @(('"' + $entry + '"')) + $options
Start-Process -FilePath $pythonw -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
