param(
    [string]$PackageVersion = "1.0.0.0",
    [string]$LicensePath = "data\EULA.rtf",
    [string]$BuildOutput = "build\__main__.dist",
    [string]$OutputName = "RimSort-$PackageVersion-Windows-64"
)

$ErrorActionPreference = "Stop"

# Helper function for consistent colored output
function Write-Info {
    param([string]$Message, [int]$Indent = 0)
    Write-Host ("  " * $Indent) + $Message -ForegroundColor Green
}

function Write-Status {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Cyan
}

Write-Status "Building RimSort MSI..."
Write-Info "PackageVersion: $PackageVersion"
Write-Info "LicensePath: $LicensePath"
Write-Info "BuildOutput: $BuildOutput"
Write-Host ""
Write-Status "Validating prerequisites..."
Write-Host ""

# Validate required files exist
if (-not (Test-Path "data\RimSort.wxs")) {
    Write-Error "WIX source file not found: data\RimSort.wxs"
    exit 1
}

if (-not (Test-Path $LicensePath)) {
    Write-Error "License file not found: $LicensePath"
    exit 1
}

if (-not (Test-Path $BuildOutput)) {
    Write-Error "Build output directory not found: $BuildOutput"
    exit 1
}

# Resolve absolute paths
$AbsoluteLicensePath = Resolve-Path $LicensePath
$AbsoluteBuildOutput = Resolve-Path $BuildOutput

Write-Status "Prerequisites validated."
Write-Host ""

# Build the MSI using wix build
$wixArgs = @(
    "build",
    "data\RimSort.wxs",
    "-ext", "WixToolset.UI.wixext",
    "-ext", "WixToolset.Util.wixext",
    "-d", "PackageVersion=$PackageVersion",
    "-d", "License=$AbsoluteLicensePath",
    "-d", "BuildOutput=$AbsoluteBuildOutput",
    "-o", "$OutputName.msi"
)

Write-Status "Please wait Building MSI..."
Write-Host ""
& wix @wixArgs
$buildExitCode = $LASTEXITCODE

if ($buildExitCode -eq 0) {
    $msiPath = Join-Path (Get-Location) "$OutputName.msi"
    $msiSize = (Get-Item $msiPath).Length / 1MB
    Write-Host ""
    Write-Host "✓ Build succeeded: $OutputName.msi ($([math]::Round($msiSize, 2)) MB)" -ForegroundColor Green
} else {
    Write-Error "Build failed with exit code $buildExitCode"
    exit $buildExitCode
}
