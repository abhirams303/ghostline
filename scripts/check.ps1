Write-Host "Running frontend lint..."
pnpm lint
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Running frontend build..."
pnpm build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Running backend tests..."
Push-Location backend
python -m pytest
$exitCode = $LASTEXITCODE
Pop-Location
exit $exitCode
