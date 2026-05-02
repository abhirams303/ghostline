[CmdletBinding()]
param(
    [string]$ClaudeSkillsPath = "$HOME\\.claude\\skills",
    [string]$CodexSkillsPath = "$HOME\\.codex\\skills",
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-NormalizedPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    return [System.IO.Path]::GetFullPath($Path)
}

if (-not (Test-Path -LiteralPath $ClaudeSkillsPath -PathType Container)) {
    throw "Claude skills directory not found: $ClaudeSkillsPath"
}

if (-not (Test-Path -LiteralPath $CodexSkillsPath -PathType Container)) {
    New-Item -ItemType Directory -Path $CodexSkillsPath -Force | Out-Null
}

$created = New-Object System.Collections.Generic.List[string]
$skipped = New-Object System.Collections.Generic.List[string]
$replaced = New-Object System.Collections.Generic.List[string]

$sourceRoot = Get-NormalizedPath -Path $ClaudeSkillsPath
$targetRoot = Get-NormalizedPath -Path $CodexSkillsPath

Get-ChildItem -LiteralPath $sourceRoot -Directory | Sort-Object Name | ForEach-Object {
    $skillName = $_.Name
    $sourcePath = $_.FullName
    $targetPath = Join-Path $targetRoot $skillName

    if (Test-Path -LiteralPath $targetPath) {
        $existingItem = Get-Item -LiteralPath $targetPath -Force
        $existingTarget = @($existingItem.Target | ForEach-Object { Get-NormalizedPath -Path $_ })
        $matchesSource = $existingItem.Attributes.HasFlag([System.IO.FileAttributes]::ReparsePoint) -and
            $existingTarget -contains (Get-NormalizedPath -Path $sourcePath)

        if ($matchesSource) {
            $skipped.Add($skillName)
            return
        }

        if (-not $Force) {
            $skipped.Add($skillName)
            return
        }

        Remove-Item -LiteralPath $targetPath -Recurse -Force
        $replaced.Add($skillName)
    }

    New-Item -ItemType Junction -Path $targetPath -Target $sourcePath | Out-Null
    $created.Add($skillName)
}

Write-Output "Claude skills source: $sourceRoot"
Write-Output "Codex skills target: $targetRoot"
Write-Output "Created: $($created.Count)"
if ($created.Count -gt 0) {
    Write-Output ($created -join ", ")
}
Write-Output "Replaced: $($replaced.Count)"
if ($replaced.Count -gt 0) {
    Write-Output ($replaced -join ", ")
}
Write-Output "Skipped: $($skipped.Count)"
if ($skipped.Count -gt 0) {
    Write-Output ($skipped -join ", ")
}
