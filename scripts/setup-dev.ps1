Write-Host "Installing frontend workspace dependencies..."
pnpm install
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Installing backend package in editable mode..."
Push-Location backend
python -m pip install -e .[dev]
$exitCode = $LASTEXITCODE
Pop-Location
exit $exitCode
