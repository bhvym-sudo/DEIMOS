$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "Starting DEIMOS services..."

$goProcess = Start-Process -FilePath "go" -ArgumentList "run", "./cmd/deimos" -WorkingDirectory "$projectRoot\backend" -WindowStyle Hidden -PassThru
$pythonProcess = Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "ai_service.app.main:app", "--host", "127.0.0.1", "--port", "8001", "--reload" -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru

try {
    npm.cmd --prefix "$projectRoot\frontend" run dev
}
finally {
    if (!$goProcess.HasExited) {
        Stop-Process -Id $goProcess.Id
    }
    if (!$pythonProcess.HasExited) {
        Stop-Process -Id $pythonProcess.Id
    }
}
