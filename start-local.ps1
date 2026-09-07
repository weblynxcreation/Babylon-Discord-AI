param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $localPython)) {
    throw 'Python environment missing. Run: py -3 -m venv .venv; then .\.venv\Scripts\python.exe -m pip install -r requirements.txt'
}
$localEntry = Join-Path $PSScriptRoot 'scripts\local_bot.py'
if ($CheckOnly) {
    & $localPython $localEntry --check
} else {
    & $localPython $localEntry
}
exit $LASTEXITCODE
