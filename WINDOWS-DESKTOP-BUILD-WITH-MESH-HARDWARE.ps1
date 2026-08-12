[CmdletBinding()]
param(
    [switch]$SkipPrerequisiteInstall,
    [switch]$SkipBrowserRuntime
)

$ErrorActionPreference = 'Stop'
$env:SB_INCLUDE_MESH_HARDWARE = '1'
try {
    & (Join-Path $PSScriptRoot 'WINDOWS-DESKTOP-ONE-CLICK.ps1') `
        -SkipPrerequisiteInstall:$SkipPrerequisiteInstall `
        -SkipBrowserRuntime:$SkipBrowserRuntime
    exit $LASTEXITCODE
}
finally {
    Remove-Item Env:SB_INCLUDE_MESH_HARDWARE -ErrorAction SilentlyContinue
}
