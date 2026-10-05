#requires -Version 5.1
param(
    [string]$InstallDirectory = (Join-Path $env:LOCALAPPDATA 'GuidoProjectors'),
    [switch]$DownloadOnly,
    [switch]$NoLaunch,
    [switch]$LibraryOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# BEGIN_RELEASE_JSON
$script:Release = @'
{
  "version": "1.3.0",
  "date": "2026-10-05",
  "image": {
    "name": "guido-projectory-rpi3-rpi4-rpi5-1.3.0.img.xz",
    "sha256": "220355fc52d5abd08de219fc7107428d385e1e77b2405b7bd694c20b449b2494",
    "bytes": 651942172,
    "extract_bytes": 2759852032,
    "extract_sha256": "49ef09439c9becd7805d69a5382b8df9985e950e73844537f3b4d5501d2f1d3a",
    "url": "https://github.com/Gartom91/guido-projectors/releases/download/v1.3.0/guido-projectory-rpi3-rpi4-rpi5-1.3.0.img.xz"
  },
  "pc": {
    "name": "ShadokProjektory-RPi.exe",
    "sha256": "fb6a3c26f9134733d2229c9636026405922f99957fc38ce1175ebf045571f869",
    "bytes": 116103376,
    "url": "https://github.com/Gartom91/guido-projectors/releases/download/v1.3.0/ShadokProjektory-RPi.exe"
  },
  "docs": {
    "name": "guido-dokumentacja.zip",
    "sha256": "253baa7782455ad6b22e35f1a07698e77dda389c21eb07547526d56d8c7252e2",
    "bytes": 24318,
    "url": "https://github.com/Gartom91/guido-projectors/releases/download/v1.3.0/guido-dokumentacja.zip"
  },
  "imager": {
    "name": "imager-v2.0.11.1.exe",
    "sha256": "94ffded522f3e2a38bdb9505440229e1411b80992a616ba16b2d7e73bd794130",
    "bytes": 22498400,
    "url": "https://github.com/raspberrypi/rpi-imager/releases/download/v2.0.11.1/imager-v2.0.11.1.exe"
  }
}
'@ | ConvertFrom-Json
# END_RELEASE_JSON

function Assert-DownloadUri([string]$Uri) {
    $parsed = [Uri]$Uri
    if ($parsed.Scheme -ne 'https' -or $parsed.Host -ne 'github.com' -or
        $parsed.UserInfo -or $parsed.Port -ne 443 -or $parsed.Query -or $parsed.Fragment -or
        $parsed.AbsolutePath -notmatch '^/(Gartom91/guido-projectors|raspberrypi/rpi-imager)/releases/download/[^/]+/[^/]+$') {
        throw "Niedozwolony adres pobierania: $Uri"
    }
}

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $algorithm.Dispose(); $stream.Dispose() }
}

function Test-Artifact([string]$Path, [string]$Sha256, [long]$Bytes) {
    if ($Sha256 -notmatch '^[a-fA-F0-9]{64}$' -or $Bytes -le 0) {
        throw 'Niepoprawna definicja pliku wydania.'
    }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    if ((Get-Item -LiteralPath $Path).Length -ne $Bytes) { return $false }
    return (Get-Sha256 $Path) -eq $Sha256
}

function Invoke-FileTransfer([string]$Uri, [string]$Destination) {
    $previousProgress = $ProgressPreference
    try {
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $Destination -TimeoutSec 1800
    } finally { $ProgressPreference = $previousProgress }
}

function Get-VerifiedFile([string]$Uri, [string]$Destination, [string]$Sha256, [long]$Bytes) {
    Assert-DownloadUri $Uri
    if (Test-Artifact $Destination $Sha256 $Bytes) {
        Write-Host "Juz pobrano i sprawdzono: $([IO.Path]::GetFileName($Destination))"
        return
    }
    $part = $Destination + '.part'
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Write-Host "Pobieranie $([IO.Path]::GetFileName($Destination)) ($([Math]::Round($Bytes / 1MB)) MB), proba $attempt/3..."
            Invoke-FileTransfer $Uri $part
            if (-not (Test-Artifact $part $Sha256 $Bytes)) {
                throw 'Plik ma niepoprawna dlugosc lub SHA256. Nie zostanie uzyty.'
            }
            Move-Item -LiteralPath $part -Destination $Destination -Force
            return
        } catch {
            if (Test-Path -LiteralPath $part) { Remove-Item -LiteralPath $part -Force }
            if ($attempt -eq 3) { throw }
            Write-Warning $_.Exception.Message
        }
    }
}

function Assert-InstallDirectory([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full.StartsWith('\\') -or $full -notmatch '^[A-Za-z]:\\') {
        throw 'Wybierz lokalny katalog na dysku PC.'
    }
    $root = [IO.Path]::GetPathRoot($full)
    if ($full.TrimEnd('\') -eq $root.TrimEnd('\')) {
        throw 'Wybierz katalog instalacji, a nie katalog glowny dysku.'
    }
    $drive = New-Object IO.DriveInfo($root)
    if ($drive.DriveType -ne [IO.DriveType]::Fixed) {
        throw 'Pliki instalatora musza byc na dysku PC, nie na karcie przeznaczonej do wymazania.'
    }
    return $full
}

function Write-ImagerCatalog([string]$Path, [string]$ImagePath) {
    $image = $script:Release.image
    $catalog = [ordered]@{
        imager = [ordered]@{
            devices = @(
                @{ name = 'Raspberry Pi 3B'; description = 'Guido: Raspberry Pi 3 Model B'; tags = @('pi3-32bit'); matching_type = 'inclusive'; capabilities = @() },
                @{ name = 'Raspberry Pi 4B'; description = 'Guido: Raspberry Pi 4 Model B'; tags = @('pi4-32bit'); matching_type = 'inclusive'; capabilities = @() },
                @{ name = 'Raspberry Pi 5'; description = 'Guido: Raspberry Pi 5'; tags = @('pi5-32bit'); matching_type = 'inclusive'; capabilities = @() }
            )
        }
        os_list = @([ordered]@{
            name = "Guido $($script:Release.version) - projektory / TUI"
            description = 'RPi 3B / 4B / 5. Konto i SSH konfigurujesz po pierwszym starcie na monitorze.'
            icon = 'https://downloads.raspberrypi.com/imager/icons/RPi_4.png'
            url = ([Uri][IO.Path]::GetFullPath($ImagePath)).AbsoluteUri
            extract_size = $image.extract_bytes
            extract_sha256 = $image.extract_sha256
            image_download_size = $image.bytes
            release_date = $script:Release.date
            devices = @('pi3-32bit', 'pi4-32bit', 'pi5-32bit')
            init_format = 'none'
            capabilities = @()
        })
    }
    $json = $catalog | ConvertTo-Json -Depth 10
    [IO.File]::WriteAllText($Path, $json, (New-Object Text.UTF8Encoding($false)))
}

function Find-Imager {
    $candidates = @()
    foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
        if ($base) {
            $candidates += Join-Path $base 'Raspberry Pi Ltd\Imager\rpi-imager.exe'
            $candidates += Join-Path $base 'Raspberry Pi Imager\rpi-imager.exe'
        }
    }
    foreach ($hive in @('HKLM:', 'HKCU:')) {
        $key = "$hive\Software\Microsoft\Windows\CurrentVersion\App Paths\rpi-imager.exe"
        if (Test-Path $key) { $candidates += (Get-Item $key).GetValue('') }
    }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            $text = (Get-Item -LiteralPath $candidate).VersionInfo.ProductVersion
            if ($text -match '(\d+\.\d+\.\d+)') {
                if ([Version]$Matches[1] -ge [Version]'2.0.0') { return $candidate }
            }
        }
    }
    return $null
}

function New-GuidoShortcut([string]$Path, [string]$Target, [string]$Arguments = '') {
    $shell = New-Object -ComObject WScript.Shell
    try {
        $shortcut = $shell.CreateShortcut($Path)
        $shortcut.TargetPath = $Target
        $shortcut.Arguments = $Arguments
        $shortcut.WorkingDirectory = Split-Path $Target -Parent
        $shortcut.Description = 'Guido - sterowanie projektorami'
        $shortcut.Save()
    } finally { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($shell) }
}

function Install-Guido {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or
        -not [Environment]::Is64BitOperatingSystem -or [Environment]::OSVersion.Version.Major -lt 10) {
        throw 'Wymagany Windows 10/11 x64.'
    }
    if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') {
        throw 'To wydanie aplikacji jest przeznaczone dla procesora x64.'
    }
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $directory = Join-Path (Assert-InstallDirectory $InstallDirectory) $script:Release.version
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $lock = $null
    try {
        try {
            $lock = [IO.File]::Open((Join-Path $directory 'installer.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        } catch { throw 'Inny instalator uzywa tego katalogu. Zamknij go i sprobuj ponownie.' }
        $drive = New-Object IO.DriveInfo([IO.Path]::GetPathRoot($directory))
        $missing = [long]0
        foreach ($artifact in @($script:Release.image, $script:Release.pc, $script:Release.docs)) {
            if (-not (Test-Artifact (Join-Path $directory $artifact.name) $artifact.sha256 $artifact.bytes)) {
                $missing += $artifact.bytes
            }
        }
        if ($drive.AvailableFreeSpace -lt ($missing + 512MB)) { throw 'Za malo miejsca: zapewnij ok. 1.5 GB wolnego na dysku PC.' }
        Write-Host "GUIDO $($script:Release.version) - karta SD i aplikacja Windows"
        Write-Host "Katalog: $directory"
        foreach ($artifact in @($script:Release.image, $script:Release.pc, $script:Release.docs)) {
            Get-VerifiedFile $artifact.url (Join-Path $directory $artifact.name) $artifact.sha256 $artifact.bytes
        }
        $imagePath = Join-Path $directory $script:Release.image.name
        $pcPath = Join-Path $directory $script:Release.pc.name
        $catalogPath = Join-Path $directory 'guido-imager.json'
        Write-ImagerCatalog $catalogPath $imagePath
        Write-Host 'Obraz, aplikacja PC i dokumentacja: SHA256 poprawne.'
        if ($DownloadOnly) { return }

        Expand-Archive -LiteralPath (Join-Path $directory $script:Release.docs.name) -DestinationPath (Join-Path $directory 'Dokumentacja') -Force
        $programs = Join-Path ([Environment]::GetFolderPath('Programs')) 'Guido Projektory'
        New-Item -ItemType Directory -Force -Path $programs | Out-Null
        New-GuidoShortcut (Join-Path $programs 'Projektory Shadok.lnk') $pcPath
        $desktop = [Environment]::GetFolderPath('Desktop')
        if ($desktop) { New-GuidoShortcut (Join-Path $desktop 'Projektory Shadok.lnk') $pcPath }

        $imager = Find-Imager
        if (-not $imager) {
            Write-Host 'Pobieram oficjalny Raspberry Pi Imager. Instalacja moze wymagac zgody UAC.'
            $tool = $script:Release.imager
            $toolPath = Join-Path $directory $tool.name
            Get-VerifiedFile $tool.url $toolPath $tool.sha256 $tool.bytes
            $process = Start-Process -FilePath $toolPath -Wait -PassThru
            if ($process.ExitCode -ne 0) { throw "Instalator Imager zakonczyl sie kodem $($process.ExitCode)." }
            $imager = Find-Imager
            if (-not $imager) { throw 'Nie znaleziono Imager po instalacji. Zainstaluj go z raspberrypi.com/software i ponow skrypt.' }
        }
        $imagerArguments = '--repo "' + $catalogPath + '"'
        New-GuidoShortcut (Join-Path $programs 'Przygotuj karte SD.lnk') $imager $imagerArguments
        Write-Host ''
        Write-Host 'W Imager wybierz RPi 3B/4B/5, system GUIDO i wlasciwa karte SD 32 GB.' -ForegroundColor Yellow
        Write-Host 'Zapis WYMAZE zawartosc wybranej karty. Sprawdz jej nazwe i pojemnosc.' -ForegroundColor Yellow
        Write-Host 'Poczekaj na koniec zapisu i weryfikacji. Konfiguracja konta/SSH: pierwszy start RPi z HDMI i klawiatura.'
        Write-Host "Aplikacja PC jest w menu Start i na pulpicie. Dokumentacja: $directory\Dokumentacja"
        if (-not $NoLaunch) { Start-Process -FilePath $imager -ArgumentList $imagerArguments | Out-Null }
    } finally { if ($lock) { $lock.Dispose() } }
}

if (-not $LibraryOnly) {
    try { Install-Guido } catch { [Console]::Error.WriteLine('BLAD: ' + $_.Exception.Message); exit 1 }
}
