#requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = if ($PSScriptRoot) { Split-Path $PSScriptRoot -Parent } else { (Get-Location).Path }
. ([scriptblock]::Create([IO.File]::ReadAllText((Join-Path $repo 'installer/Install-Guido.ps1')))) -LibraryOnly
$script:Checks = 0

function Assert-True($Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
    $script:Checks++
}

function Assert-Throws([scriptblock]$Action, [string]$Message) {
    $threw = $false
    try { & $Action | Out-Null } catch { $threw = $true }
    Assert-True $threw $Message
}

$testDirectory = Join-Path ([IO.Path]::GetTempPath()) ('guido-installer-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testDirectory | Out-Null
try {
    $uri = 'https://github.com/Gartom91/guido-projectors/releases/download/v1.1.0/test.bin'
    Assert-DownloadUri $uri
    foreach ($bad in @('http://github.com/Gartom91/guido-projectors/releases/download/v1.1.0/a',
        'https://github.com.evil.invalid/Gartom91/guido-projectors/releases/download/v1.1.0/a',
        'https://github.com/other/project/releases/download/v1/a',
        'https://user@github.com/Gartom91/guido-projectors/releases/download/v1/a',
        'https://github.com:444/Gartom91/guido-projectors/releases/download/v1/a',
        'https://github.com/Gartom91/guido-projectors/releases/download/v1/a?token=secret')) {
        Assert-Throws { Assert-DownloadUri $bad } 'Unsafe URL accepted'
    }
    Assert-Throws { Assert-InstallDirectory 'C:\' } 'Root directory accepted'
    Assert-Throws { Assert-InstallDirectory '\\localhost\share\folder' } 'Network path accepted'
    Assert-True ((Assert-InstallDirectory $testDirectory) -eq $testDirectory) 'Fixed local directory rejected'
    $script:Payload = [Text.Encoding]::UTF8.GetBytes('verified fixture')
    $fixture = Join-Path $testDirectory 'fixture.bin'
    [IO.File]::WriteAllBytes($fixture, $script:Payload)
    $hash = (Get-FileHash -LiteralPath $fixture).Hash
    $bytes = $script:Payload.Length
    Assert-True (Test-Artifact $fixture $hash $bytes) 'Valid hash rejected'
    Assert-True (-not (Test-Artifact $fixture ('0' * 64) $bytes)) 'Bad hash accepted'
    Assert-True (-not (Test-Artifact $fixture $hash ($bytes + 1))) 'Wrong length accepted'
    Assert-Throws { Test-Artifact $fixture 'invalid' $bytes } 'Invalid digest accepted'

    $script:Transfers = 0
    $script:CorruptAttempts = 0
    function Invoke-FileTransfer([string]$Uri, [string]$Destination) {
        $script:Transfers++
        if ($script:Transfers -le $script:CorruptAttempts) {
            [IO.File]::WriteAllText($Destination, 'corrupt')
        } else { [IO.File]::WriteAllBytes($Destination, $script:Payload) }
    }
    $download = Join-Path $testDirectory 'download.bin'
    Get-VerifiedFile $uri $download $hash $bytes
    Assert-True ($script:Transfers -eq 1 -and (Test-Artifact $download $hash $bytes)) 'Download not verified'
    Get-VerifiedFile $uri $download $hash $bytes
    Assert-True ($script:Transfers -eq 1) 'Valid cached file downloaded again'

    $script:Transfers = 0
    $script:CorruptAttempts = 1
    $retry = Join-Path $testDirectory 'retry.bin'
    Get-VerifiedFile $uri $retry $hash $bytes
    Assert-True ($script:Transfers -eq 2 -and (Test-Artifact $retry $hash $bytes)) 'Corrupt download retry failed'
    Assert-True (-not (Test-Path ($retry + '.part'))) 'Partial file left after success'
    $script:Transfers = 0
    $script:CorruptAttempts = 3
    Assert-Throws { Get-VerifiedFile $uri $download ('f' * 64) $bytes } 'Corrupt download accepted'
    Assert-True ($script:Transfers -eq 3) 'Download retry limit incorrect'
    Assert-True (Test-Artifact $download $hash $bytes) 'Failed download overwrote existing artifact'
    Assert-True (-not (Test-Path ($download + '.part'))) 'Partial file left after failure'

    $catalogPath = Join-Path $testDirectory 'catalog.json'
    $imagePath = Join-Path $testDirectory 'name with spaces & symbols.img.xz'
    Write-ImagerCatalog $catalogPath $imagePath
    $catalog = Get-Content -LiteralPath $catalogPath -Raw | ConvertFrom-Json
    Assert-True ($catalog.os_list.Count -eq 1) 'Unexpected OS entry count'
    Assert-True ($catalog.os_list[0].init_format -eq 'none') 'Customization unexpectedly enabled'
    Assert-True ($catalog.os_list[0].extract_sha256 -eq $Release.image.extract_sha256) 'Uncompressed image hash not passed to Imager'
    Assert-True (([Uri]$catalog.os_list[0].url).LocalPath -eq $imagePath) 'File URI damaged spaces or symbols'
    Assert-True ($catalog.imager.devices.Count -eq 3 -and $catalog.os_list[0].devices.Count -eq 3) 'Boards missing'
    foreach ($board in $catalog.imager.devices) {
        Assert-True ($board.tags.Count -eq 1 -and $catalog.os_list[0].devices -contains $board.tags[0]) 'OS hidden for a supported board'
    }
    $pi5 = @($catalog.imager.devices | Where-Object { $_.name -eq 'Raspberry Pi 5' })
    Assert-True ($pi5.Count -eq 1 -and $pi5[0].tags[0] -eq 'pi5-32bit') 'Pi 5 requires the official armhf catalog tag'

    $shortcutPath = Join-Path $testDirectory 'test.lnk'
    New-GuidoShortcut $shortcutPath $env:ComSpec '/c exit 0'
    $shell = New-Object -ComObject WScript.Shell
    try {
        $shortcut = $shell.CreateShortcut($shortcutPath)
        Assert-True ($shortcut.TargetPath -eq $env:ComSpec -and $shortcut.Arguments -eq '/c exit 0') 'Shortcut target damaged'
    } finally { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($shell) }

    # Complete download-only flow with transport fixtures, no GUI, installer or public shortcuts.
    $script:CorruptAttempts = 0
    $script:Transfers = 0
    $script:Release = [pscustomobject]@{
        version = '9.9.9'; date = '2026-10-02'
        image = [pscustomobject]@{ name = 'fixture.img.xz'; sha256 = $hash; bytes = $bytes; extract_bytes = 512; extract_sha256 = $hash; url = $uri }
        pc = [pscustomobject]@{ name = 'fixture.exe'; sha256 = $hash; bytes = $bytes; url = $uri }
        docs = [pscustomobject]@{ name = 'fixture.zip'; sha256 = $hash; bytes = $bytes; url = $uri }
    }
    $InstallDirectory = Join-Path $testDirectory 'installation'
    $DownloadOnly = $true
    Install-Guido
    Assert-True ($script:Transfers -eq 3) 'Complete flow missed a payload'
    Assert-True (Test-Path (Join-Path $InstallDirectory '9.9.9/guido-imager.json')) 'Complete flow missing catalog'
    Install-Guido
    Assert-True ($script:Transfers -eq 3) 'Complete flow cache not reused'
    $report = @{ ok = $true; checks = $script:Checks; powershell = $PSVersionTable.PSVersion.ToString() } | ConvertTo-Json -Compress
    Write-Output $report
} finally {
    # Test-owned temporary directory, verified under the system temp directory.
    if ([IO.Path]::GetFullPath($testDirectory).StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()), [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $testDirectory -Recurse -Force
    }
}
