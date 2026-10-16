$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BaseZip = Join-Path $Root 'SRW_v0.8.8_Windows_Portable.zip'
$ExpectedBaseSha = 'f12933a1f6639168911af3788d207ced521be8a50841d7d39e7a2169eed3d5ab'
$OutZip = Join-Path (Split-Path -Parent $Root) 'SRW_v1.0_Business_Convergence_07_08x_Capability_Recovery_Windows_Native.zip'
function Sha($p){(Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLowerInvariant()}
if(!(Test-Path -LiteralPath $BaseZip)){throw "Missing exact carrier: $BaseZip"}
$sha=Sha $BaseZip
if($sha -ne $ExpectedBaseSha){throw "v0.8.8 carrier SHA-256 mismatch. Expected $ExpectedBaseSha got $sha"}
$tmp=Join-Path $env:TEMP ('srw-conv07-native-'+[guid]::NewGuid().ToString('N'))
$base=Join-Path $tmp 'base';$stage=Join-Path $tmp 'stage';New-Item -ItemType Directory -Force -Path $base,$stage|Out-Null
try{
  Expand-Archive -LiteralPath $BaseZip -DestinationPath $base -Force
  $children=@(Get-ChildItem -LiteralPath $base)
  $baseRoot=if($children.Count -eq 1 -and $children[0].PSIsContainer){$children[0].FullName}else{$base}
  $host=Join-Path $baseRoot 'windows-host\SmartRecruitmentWorkbench.exe'
  $truth=Join-Path $baseRoot 'windows-host\DOTNET_BUILD_TRUTH.json'
  if(!(Test-Path $host) -or !(Test-Path $truth)){throw 'Carrier does not contain the audited 0.8.x windows-host.'}
  Copy-Item -Path (Join-Path $Root '*') -Destination $stage -Recurse -Force
  Remove-Item -LiteralPath (Join-Path $stage 'SRW_v0.8.8_Windows_Portable.zip') -Force -ErrorAction SilentlyContinue
  Copy-Item -LiteralPath (Join-Path $baseRoot 'windows-host') -Destination (Join-Path $stage 'windows-host') -Recurse -Force
  $truthObj=Get-Content -Raw -LiteralPath (Join-Path $stage 'windows-host\DOTNET_BUILD_TRUTH.json')|ConvertFrom-Json
  $hostSha=Sha (Join-Path $stage 'windows-host\SmartRecruitmentWorkbench.exe')
  if($truthObj.outputs.executable_sha256 -and $hostSha -ne ([string]$truthObj.outputs.executable_sha256).ToLowerInvariant()){throw 'Inherited Host EXE hash does not match carrier DOTNET_BUILD_TRUTH.'}
  foreach($p in @('VERSION','BUILD_INFO.json','scripts\run_local.py','frontend\dist\index.html','runtime\python.exe')){if(!(Test-Path (Join-Path $stage $p))){throw "Host ABI file missing: $p"}}
  $env:PYTHONUTF8='1';$env:PYTHONDONTWRITEBYTECODE='1'
  & (Join-Path $stage 'runtime\python.exe') (Join-Path $stage 'scripts\launch_alpha10.py') --check
  if($LASTEXITCODE -ne 0){throw 'Embedded Python self-check failed.'}
  $ver=(Get-Content -Raw -LiteralPath (Join-Path $stage 'VERSION')).Trim()
  $prov=[ordered]@{schema='srw.windows-native-host-inheritance.v1';target_version=$ver;carrier_version='0.8.8';carrier_sha256=$sha;host_executable_sha256=$hostSha;host_abi='runtime-v1 + run_local + root frontend';claim_boundary='WPF/WebView2 Host binary is inherited byte-for-byte from the exact v0.8.8 carrier. Convergence backend ABI is verified by automated tests and embedded self-check. Exact-artifact GUI acceptance still requires Windows smoke.'}
  New-Item -ItemType Directory -Force -Path (Join-Path $stage 'verification')|Out-Null
  $prov|ConvertTo-Json -Depth 8|Set-Content -Encoding UTF8 -LiteralPath (Join-Path $stage 'verification\INHERITED_WINDOWS_HOST_PROVENANCE_CONVERGENCE07.json')
  Remove-Item -LiteralPath $OutZip -Force -ErrorAction SilentlyContinue
  Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $OutZip -CompressionLevel Optimal
  $outSha=Sha $OutZip
  Set-Content -Encoding ASCII -LiteralPath ($OutZip+'.sha256') -Value "$outSha  $(Split-Path -Leaf $OutZip)"
  Write-Host "Windows Native assembly complete: $OutZip" -ForegroundColor Green
  Write-Host "SHA-256: $outSha" -ForegroundColor Green
  Write-Host 'Exact Windows GUI smoke remains required before promoting runtime truth.' -ForegroundColor Yellow
} finally {Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue}
