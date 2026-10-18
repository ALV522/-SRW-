$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BaseZip = Join-Path $Root 'SRW_v0.8.8_Windows_Portable.zip'
$ExpectedBaseSha = 'f12933a1f6639168911af3788d207ced521be8a50841d7d39e7a2169eed3d5ab'
$Version = (Get-Content -Raw -LiteralPath (Join-Path $Root 'VERSION')).Trim()
$VersionSlug = $Version -replace '[^a-zA-Z0-9._-]', '_'
$OutZip = Join-Path (Split-Path -Parent $Root) ("SRW_" + $VersionSlug + "_Windows_Native_UNVERIFIED.zip")
function Sha($p) { (Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLowerInvariant() }

# Verify the carrier digest without executing any externally supplied binaries.
if (!(Test-Path -LiteralPath $BaseZip)) { throw "Missing exact carrier: $BaseZip" }
$carrierSha = Sha $BaseZip
if ($carrierSha -ne $ExpectedBaseSha) { throw "Audited Windows carrier SHA mismatch." }

function CopyReviewedSources($rootDir, $stageDir) {
  $manifest = Join-Path $rootDir 'SOURCE_MANIFEST.sha256'
  if (!(Test-Path -LiteralPath $manifest)) { throw 'SOURCE_MANIFEST.sha256 missing' }
  foreach ($line in (Get-Content -LiteralPath $manifest -Encoding UTF8)) {
    if (![string]::IsNullOrWhiteSpace($line)) {
      if ($line -match '^([0-9a-fA-F]{64})  (.+)$') { } else { throw 'Malformed source manifest entry' }
      $expected = $Matches[1].ToLowerInvariant()
      $relative = $Matches[2]
      if ($relative -match '^[\\/]' -or $relative -match '^[a-zA-Z]:' -or $relative.Contains('\')) {
        throw 'Unsafe source manifest path'
      }
      foreach ($segment in $relative.Split('/')) {
        if ([string]::IsNullOrWhiteSpace($segment) -or $segment -in @('.', '..')) {
          throw 'Unsafe source manifest path segment'
        }
      }
      $relativeWin = $relative.Replace('/', '\')
      $src = Join-Path $rootDir $relativeWin
      $dst = Join-Path $stageDir $relativeWin
      if (!(Test-Path -LiteralPath $src -PathType Leaf)) { throw "Missing reviewed source: $relative" }
      if ((Sha $src) -ne $expected) { throw "Source hash mismatch: $relative" }
      New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
      Copy-Item -LiteralPath $src -Destination $dst -Force
    }
  }
  Copy-Item -LiteralPath $manifest -Destination (Join-Path $stageDir 'SOURCE_MANIFEST.sha256') -Force
}

function CopyAuditedRuntime($runtimeRoot, $runtimeManifest, $runtimeStage) {
  if (!(Test-Path -LiteralPath $runtimeManifest -PathType Leaf)) { throw 'Audited Runtime inventory missing' }
  if (!(Test-Path -LiteralPath $runtimeRoot -PathType Container)) { throw 'Runtime source directory missing' }
  if ((Get-Item -LiteralPath $runtimeRoot).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Runtime root is a symlink' }
  $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
  New-Item -ItemType Directory -Force -Path $runtimeStage | Out-Null
  foreach ($line in (Get-Content -LiteralPath $runtimeManifest -Encoding UTF8)) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    if ($line -notmatch '^([0-9a-fA-F]{64})  (.+)
$base = Join-Path $tmp 'carrier'
$stage = Join-Path $tmp 'stage'
New-Item -ItemType Directory -Force -Path $base,$stage | Out-Null
try {
  # Source and Runtime are independently checked before any embedded Python is launched.
  CopyReviewedSources $Root $stage
  CopyAuditedRuntime (Join-Path $Root 'runtime') (Join-Path $Root 'PRODUCTION_RUNTIME.sha256') (Join-Path $stage 'runtime')
  $RuntimePython = Join-Path $stage 'runtime\python.exe'
  & $RuntimePython (Join-Path $stage 'scripts\portable_input_preflight.py') `
    --root $Root --runtime (Join-Path $stage 'runtime') `
    --runtime-manifest (Join-Path $Root 'PRODUCTION_RUNTIME.sha256')
  if ($LASTEXITCODE -ne 0) { throw 'Portable preflight BLOCKED; no Native candidate was built' }
  Expand-Archive -LiteralPath $BaseZip -DestinationPath $base -Force
  $children = @(Get-ChildItem -LiteralPath $base)
  $baseRoot = if ($children.Count -eq 1 -and $children[0].PSIsContainer) { $children[0].FullName } else { $base }
  $hostExe = Join-Path $baseRoot 'windows-host\SmartRecruitmentWorkbench.exe'
  $hostTruth = Join-Path $baseRoot 'windows-host\DOTNET_BUILD_TRUTH.json'
  if (!(Test-Path -LiteralPath $hostExe) -or !(Test-Path -LiteralPath $hostTruth)) {
    throw 'Exact carrier is missing the audited 0.8.x Windows Host.'
  }

  # Only manifest-reviewed source and external audited asset bytes enter the stage.
  Copy-Item -LiteralPath (Join-Path $Root 'PRODUCTION_RUNTIME.sha256') -Destination (Join-Path $stage 'PRODUCTION_RUNTIME.sha256') -Force
  foreach ($name in @('taxonomy','job_info','competency','market_reference','reference')) {
    $srcDb = Join-Path (Join-Path (Join-Path $Root 'knowledge\active') $name) 'knowledge.db'
    $dstDb = Join-Path (Join-Path (Join-Path $stage 'knowledge\active') $name) 'knowledge.db'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dstDb) | Out-Null
    Copy-Item -LiteralPath $srcDb -Destination $dstDb -Force
  }
  Copy-Item -LiteralPath (Join-Path $Root 'PRODUCTION_KNOWLEDGE.sha256') -Destination (Join-Path $stage 'PRODUCTION_KNOWLEDGE.sha256') -Force
  Copy-Item -LiteralPath (Join-Path $baseRoot 'windows-host') -Destination $stage -Recurse -Force

  $truthObj = Get-Content -Raw -LiteralPath (Join-Path $stage 'windows-host\DOTNET_BUILD_TRUTH.json') | ConvertFrom-Json
  $hostSha = Sha (Join-Path $stage 'windows-host\SmartRecruitmentWorkbench.exe')
  if ($truthObj.outputs.executable_sha256 -and $hostSha -ne ([string]$truthObj.outputs.executable_sha256).ToLowerInvariant()) {
    throw 'Inherited Windows Host binary fails carrier truth SHA-256.'
  }
  foreach ($p in @('VERSION','BUILD_INFO.json','scripts\run_local.py','frontend\dist\index.html','runtime\python.exe')) {
    if (!(Test-Path -LiteralPath (Join-Path $stage $p))) { throw "Host ABI file missing: $p" }
  }
  $env:PYTHONUTF8 = '1'; $env:PYTHONDONTWRITEBYTECODE = '1'
  & (Join-Path $stage 'runtime\python.exe') (Join-Path $stage 'scripts\launch_alpha10.py') --check
  if ($LASTEXITCODE -ne 0) { throw 'Embedded Python self-check failed' }

  $provenance = [ordered]@{
    schema = 'srw.windows-native-host-inheritance.v1'
    target_version = $Version
    carrier_version = '0.8.8'
    carrier_sha256 = $carrierSha
    host_executable_sha256 = $hostSha
    source_manifest_sha256 = (Sha (Join-Path $stage 'SOURCE_MANIFEST.sha256'))
    runtime_manifest_sha256 = (Sha (Join-Path $stage 'PRODUCTION_RUNTIME.sha256'))
    artifact_status = 'UNVERIFIED_GUI'
    claim_boundary = 'Only reviewed source and explicitly validated external assets were staged. No runtime or WPF/WebView2 GUI acceptance is implied by assembly.'
  }
  New-Item -ItemType Directory -Force -Path (Join-Path $stage 'verification') | Out-Null
  $provenance | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $stage 'verification\INHERITED_WINDOWS_HOST_PROVENANCE.json')
  Remove-Item -LiteralPath $OutZip -Force -ErrorAction SilentlyContinue
  Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $OutZip -CompressionLevel Optimal
  # Validate the actual compressed output, not only the staging tree.
  & $RuntimePython (Join-Path $stage 'scripts\native_payload.py') audit-zip `
    --zip $OutZip --source-root $Root --host-root (Join-Path $baseRoot 'windows-host')
  if ($LASTEXITCODE -ne 0) {
    Remove-Item -LiteralPath $OutZip -Force -ErrorAction SilentlyContinue
    throw 'Native ZIP allowlist/hash validation BLOCKED'
  }
  $outSha = Sha $OutZip
  Set-Content -Encoding ASCII -LiteralPath ($OutZip + '.sha256') -Value "$outSha  $(Split-Path -Leaf $OutZip)"
  Write-Host "Windows Native candidate assembled: $OutZip" -ForegroundColor Green
  Write-Host "SHA-256: $outSha" -ForegroundColor Green
  Write-Host 'Exact Windows GUI smoke remains required before any release promotion; WPF/WebView2 business acceptance is also pending.' -ForegroundColor Yellow
} finally {
  Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
) { throw 'Malformed external Runtime inventory' }
    $digest = $Matches[1].ToLowerInvariant()
    $relative = $Matches[2]
    if (!$seen.Add($relative)) { throw 'Duplicate or case-colliding Runtime entry' }
    if ($relative -match '^[\\/]' -or $relative -match ':' -or $relative.Contains('\')) { throw 'Unsafe Runtime inventory path' }
    $parts = @($relative.Split('/'))
    foreach ($part in $parts) {
      if ([string]::IsNullOrWhiteSpace($part) -or $part -eq '.' -or $part -eq '..' -or $part.EndsWith('.') -or $part.EndsWith(' ')) { throw 'Unsafe Runtime path segment' }
      if ($part -in @('data','backups','backup','uploads','workspace','candidates','secrets','credentials','private','logs')) { throw 'Private Runtime inventory directory prohibited' }
    }
    if ($parts[-1] -in @('.env','provider_secrets.json','secrets.json','credentials.json') -or $parts[-1] -match '\.(pem|key|pfx|p12|db|sqlite)
$base = Join-Path $tmp 'carrier'
$stage = Join-Path $tmp 'stage'
New-Item -ItemType Directory -Force -Path $base,$stage | Out-Null
try {
  Expand-Archive -LiteralPath $BaseZip -DestinationPath $base -Force
  $children = @(Get-ChildItem -LiteralPath $base)
  $baseRoot = if ($children.Count -eq 1 -and $children[0].PSIsContainer) { $children[0].FullName } else { $base }
  $hostExe = Join-Path $baseRoot 'windows-host\SmartRecruitmentWorkbench.exe'
  $hostTruth = Join-Path $baseRoot 'windows-host\DOTNET_BUILD_TRUTH.json'
  if (!(Test-Path -LiteralPath $hostExe) -or !(Test-Path -LiteralPath $hostTruth)) {
    throw 'Exact carrier is missing the audited 0.8.x Windows Host.'
  }

  # Manifest allowlist: never recursively copy Root/* (which may contain
  # candidate data, backups, API keys, temporary files or unrelated ZIPs).
  CopyReviewedSources $Root $stage

  # The three externally supplied artifact families are explicitly staged.
  # Runtime bytes are staged from independently audited SHA-256 inventory only.
  & $RuntimePython (Join-Path $Root 'scripts\native_payload.py') stage-runtime `
    --runtime (Join-Path $Root 'runtime') `
    --manifest (Join-Path $Root 'PRODUCTION_RUNTIME.sha256') `
    --destination (Join-Path $stage 'runtime')
  if ($LASTEXITCODE -ne 0) { throw 'Audited Runtime staging BLOCKED' }
  Copy-Item -LiteralPath (Join-Path $Root 'PRODUCTION_RUNTIME.sha256') -Destination (Join-Path $stage 'PRODUCTION_RUNTIME.sha256') -Force
  foreach ($name in @('taxonomy','job_info','competency','market_reference','reference')) {
    $srcDb = Join-Path (Join-Path (Join-Path $Root 'knowledge\active') $name) 'knowledge.db'
    $dstDb = Join-Path (Join-Path (Join-Path $stage 'knowledge\active') $name) 'knowledge.db'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dstDb) | Out-Null
    Copy-Item -LiteralPath $srcDb -Destination $dstDb -Force
  }
  Copy-Item -LiteralPath (Join-Path $Root 'PRODUCTION_KNOWLEDGE.sha256') -Destination (Join-Path $stage 'PRODUCTION_KNOWLEDGE.sha256') -Force
  Copy-Item -LiteralPath (Join-Path $baseRoot 'windows-host') -Destination $stage -Recurse -Force

  $truthObj = Get-Content -Raw -LiteralPath (Join-Path $stage 'windows-host\DOTNET_BUILD_TRUTH.json') | ConvertFrom-Json
  $hostSha = Sha (Join-Path $stage 'windows-host\SmartRecruitmentWorkbench.exe')
  if ($truthObj.outputs.executable_sha256 -and $hostSha -ne ([string]$truthObj.outputs.executable_sha256).ToLowerInvariant()) {
    throw 'Inherited Windows Host binary fails carrier truth SHA-256.'
  }
  foreach ($p in @('VERSION','BUILD_INFO.json','scripts\run_local.py','frontend\dist\index.html','runtime\python.exe')) {
    if (!(Test-Path -LiteralPath (Join-Path $stage $p))) { throw "Host ABI file missing: $p" }
  }
  $env:PYTHONUTF8 = '1'; $env:PYTHONDONTWRITEBYTECODE = '1'
  & (Join-Path $stage 'runtime\python.exe') (Join-Path $stage 'scripts\launch_alpha10.py') --check
  if ($LASTEXITCODE -ne 0) { throw 'Embedded Python self-check failed' }

  $provenance = [ordered]@{
    schema = 'srw.windows-native-host-inheritance.v1'
    target_version = $Version
    carrier_version = '0.8.8'
    carrier_sha256 = $carrierSha
    host_executable_sha256 = $hostSha
    source_manifest_sha256 = (Sha (Join-Path $stage 'SOURCE_MANIFEST.sha256'))
    runtime_manifest_sha256 = (Sha (Join-Path $stage 'PRODUCTION_RUNTIME.sha256'))
    artifact_status = 'UNVERIFIED_GUI'
    claim_boundary = 'Only reviewed source and explicitly validated external assets were staged. No runtime or WPF/WebView2 GUI acceptance is implied by assembly.'
  }
  New-Item -ItemType Directory -Force -Path (Join-Path $stage 'verification') | Out-Null
  $provenance | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $stage 'verification\INHERITED_WINDOWS_HOST_PROVENANCE.json')
  Remove-Item -LiteralPath $OutZip -Force -ErrorAction SilentlyContinue
  Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $OutZip -CompressionLevel Optimal
  # Validate the actual compressed output, not only the staging tree.
  & $RuntimePython (Join-Path $Root 'scripts\native_payload.py') audit-zip `
    --zip $OutZip --source-root $Root --host-root (Join-Path $baseRoot 'windows-host')
  if ($LASTEXITCODE -ne 0) {
    Remove-Item -LiteralPath $OutZip -Force -ErrorAction SilentlyContinue
    throw 'Native ZIP allowlist/hash validation BLOCKED'
  }
  $outSha = Sha $OutZip
  Set-Content -Encoding ASCII -LiteralPath ($OutZip + '.sha256') -Value "$outSha  $(Split-Path -Leaf $OutZip)"
  Write-Host "Windows Native candidate assembled: $OutZip" -ForegroundColor Green
  Write-Host "SHA-256: $outSha" -ForegroundColor Green
  Write-Host 'Exact Windows GUI smoke remains required before any release promotion; WPF/WebView2 business acceptance is also pending.' -ForegroundColor Yellow
} finally {
  Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
) { throw 'Private Runtime inventory file prohibited' }
    $source = $runtimeRoot
    foreach ($part in $parts) {
      $source = Join-Path $source $part
      if (!(Test-Path -LiteralPath $source)) { throw 'Audited Runtime file missing' }
      if ((Get-Item -LiteralPath $source).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Audited Runtime contains a symlink' }
    }
    if (!(Test-Path -LiteralPath $source -PathType Leaf)) { throw 'Audited Runtime entry is not a file' }
    if ((Sha $source) -ne $digest) { throw 'Runtime source SHA mismatch' }
    $target = Join-Path $runtimeStage ($relative.Replace('/', '\'))
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
    if ((Sha $target) -ne $digest) { throw 'Staged Runtime SHA mismatch' }
  }
  if (!$seen.Contains('python.exe')) { throw 'Runtime inventory lacks python.exe' }
}
$tmp = Join-Path $env:TEMP ('srw-c11-native-' + [guid]::NewGuid().ToString('N'))
$base = Join-Path $tmp 'carrier'
$stage = Join-Path $tmp 'stage'
New-Item -ItemType Directory -Force -Path $base,$stage | Out-Null
try {
  Expand-Archive -LiteralPath $BaseZip -DestinationPath $base -Force
  $children = @(Get-ChildItem -LiteralPath $base)
  $baseRoot = if ($children.Count -eq 1 -and $children[0].PSIsContainer) { $children[0].FullName } else { $base }
  $hostExe = Join-Path $baseRoot 'windows-host\SmartRecruitmentWorkbench.exe'
  $hostTruth = Join-Path $baseRoot 'windows-host\DOTNET_BUILD_TRUTH.json'
  if (!(Test-Path -LiteralPath $hostExe) -or !(Test-Path -LiteralPath $hostTruth)) {
    throw 'Exact carrier is missing the audited 0.8.x Windows Host.'
  }

  # Manifest allowlist: never recursively copy Root/* (which may contain
  # candidate data, backups, API keys, temporary files or unrelated ZIPs).
  CopyReviewedSources $Root $stage

  # The three externally supplied artifact families are explicitly staged.
  # Runtime bytes are staged from independently audited SHA-256 inventory only.
  & $RuntimePython (Join-Path $Root 'scripts\native_payload.py') stage-runtime `
    --runtime (Join-Path $Root 'runtime') `
    --manifest (Join-Path $Root 'PRODUCTION_RUNTIME.sha256') `
    --destination (Join-Path $stage 'runtime')
  if ($LASTEXITCODE -ne 0) { throw 'Audited Runtime staging BLOCKED' }
  Copy-Item -LiteralPath (Join-Path $Root 'PRODUCTION_RUNTIME.sha256') -Destination (Join-Path $stage 'PRODUCTION_RUNTIME.sha256') -Force
  foreach ($name in @('taxonomy','job_info','competency','market_reference','reference')) {
    $srcDb = Join-Path (Join-Path (Join-Path $Root 'knowledge\active') $name) 'knowledge.db'
    $dstDb = Join-Path (Join-Path (Join-Path $stage 'knowledge\active') $name) 'knowledge.db'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dstDb) | Out-Null
    Copy-Item -LiteralPath $srcDb -Destination $dstDb -Force
  }
  Copy-Item -LiteralPath (Join-Path $Root 'PRODUCTION_KNOWLEDGE.sha256') -Destination (Join-Path $stage 'PRODUCTION_KNOWLEDGE.sha256') -Force
  Copy-Item -LiteralPath (Join-Path $baseRoot 'windows-host') -Destination $stage -Recurse -Force

  $truthObj = Get-Content -Raw -LiteralPath (Join-Path $stage 'windows-host\DOTNET_BUILD_TRUTH.json') | ConvertFrom-Json
  $hostSha = Sha (Join-Path $stage 'windows-host\SmartRecruitmentWorkbench.exe')
  if ($truthObj.outputs.executable_sha256 -and $hostSha -ne ([string]$truthObj.outputs.executable_sha256).ToLowerInvariant()) {
    throw 'Inherited Windows Host binary fails carrier truth SHA-256.'
  }
  foreach ($p in @('VERSION','BUILD_INFO.json','scripts\run_local.py','frontend\dist\index.html','runtime\python.exe')) {
    if (!(Test-Path -LiteralPath (Join-Path $stage $p))) { throw "Host ABI file missing: $p" }
  }
  $env:PYTHONUTF8 = '1'; $env:PYTHONDONTWRITEBYTECODE = '1'
  & (Join-Path $stage 'runtime\python.exe') (Join-Path $stage 'scripts\launch_alpha10.py') --check
  if ($LASTEXITCODE -ne 0) { throw 'Embedded Python self-check failed' }

  $provenance = [ordered]@{
    schema = 'srw.windows-native-host-inheritance.v1'
    target_version = $Version
    carrier_version = '0.8.8'
    carrier_sha256 = $carrierSha
    host_executable_sha256 = $hostSha
    source_manifest_sha256 = (Sha (Join-Path $stage 'SOURCE_MANIFEST.sha256'))
    runtime_manifest_sha256 = (Sha (Join-Path $stage 'PRODUCTION_RUNTIME.sha256'))
    artifact_status = 'UNVERIFIED_GUI'
    claim_boundary = 'Only reviewed source and explicitly validated external assets were staged. No runtime or WPF/WebView2 GUI acceptance is implied by assembly.'
  }
  New-Item -ItemType Directory -Force -Path (Join-Path $stage 'verification') | Out-Null
  $provenance | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $stage 'verification\INHERITED_WINDOWS_HOST_PROVENANCE.json')
  Remove-Item -LiteralPath $OutZip -Force -ErrorAction SilentlyContinue
  Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $OutZip -CompressionLevel Optimal
  # Validate the actual compressed output, not only the staging tree.
  & $RuntimePython (Join-Path $Root 'scripts\native_payload.py') audit-zip `
    --zip $OutZip --source-root $Root --host-root (Join-Path $baseRoot 'windows-host')
  if ($LASTEXITCODE -ne 0) {
    Remove-Item -LiteralPath $OutZip -Force -ErrorAction SilentlyContinue
    throw 'Native ZIP allowlist/hash validation BLOCKED'
  }
  $outSha = Sha $OutZip
  Set-Content -Encoding ASCII -LiteralPath ($OutZip + '.sha256') -Value "$outSha  $(Split-Path -Leaf $OutZip)"
  Write-Host "Windows Native candidate assembled: $OutZip" -ForegroundColor Green
  Write-Host "SHA-256: $outSha" -ForegroundColor Green
  Write-Host 'Exact Windows GUI smoke remains required before any release promotion; WPF/WebView2 business acceptance is also pending.' -ForegroundColor Yellow
} finally {
  Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
