<#
.SYNOPSIS
    Llack 개발 명령 (윈도우용) — Makefile 과 같은 역할입니다.

.DESCRIPTION
    윈도우에는 make 가 기본 설치되어 있지 않으므로, Makefile 의 타깃을
    그대로 옮긴 PowerShell 디스패처입니다.

.EXAMPLE
    .\llack.ps1 setup
    .\llack.ps1 seed
    .\llack.ps1 dev
    .\llack.ps1 desktop

.NOTES
    처음 실행 시 스크립트 실행이 차단되면 아래를 한 번 실행하세요.
      Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Task = "help",

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root    = $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Desktop = Join-Path $Root "desktop"
$Sdk     = Join-Path $Root "packages\llack-app-sdk"

# 윈도우 venv 는 bin 이 아니라 Scripts 입니다.
$VenvBin = Join-Path $Backend ".venv\Scripts"
$Py      = Join-Path $VenvBin "python.exe"
$Pip     = Join-Path $VenvBin "pip.exe"
$Uvicorn = Join-Path $VenvBin "uvicorn.exe"
$Alembic = Join-Path $VenvBin "alembic.exe"
$Pytest  = Join-Path $VenvBin "pytest.exe"
$Ruff    = Join-Path $VenvBin "ruff.exe"

# 개발용 기본값. 실제 배포에서는 반드시 덮어쓰세요.
if (-not $env:LLACK_DATABASE_URL) {
    $env:LLACK_DATABASE_URL = "sqlite+aiosqlite:///./var/llack-dev.db"
}
if (-not $env:LLACK_SECRET_KEY) {
    $env:LLACK_SECRET_KEY = "dev-secret-not-for-production-0123456789"
}
if (-not $env:LLACK_ENV) {
    $env:LLACK_ENV = "development"
}

function Write-Step($message) {
    Write-Host "==> $message" -ForegroundColor Cyan
}

function Write-Ok($message) {
    Write-Host "    $message" -ForegroundColor Green
}

function Invoke-In($directory, [scriptblock]$body) {
    Push-Location $directory
    try { & $body }
    finally { Pop-Location }
}

# 필수 도구가 있는지 먼저 확인하고, 없으면 설치 방법을 알려줍니다.
function Assert-Tool($command, $label, $howTo) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "$label 를 찾을 수 없습니다. 설치 방법: $howTo"
    }
}

function Resolve-Python {
    # 윈도우에서는 py 런처가 가장 확실합니다.
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($version in @("3.13", "3.12", "3.11")) {
            & py "-$version" --version *> $null
            if ($LASTEXITCODE -eq 0) { return @("py", "-$version") }
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $reported = (& python --version 2>&1)
        if ($reported -match "Python 3\.(1[1-9]|[2-9][0-9])") { return @("python") }
        throw "Python 3.11 이상이 필요합니다. 현재: $reported"
    }
    throw "Python 을 찾을 수 없습니다. 설치: winget install Python.Python.3.12"
}

function Task-Help {
    Write-Host ""
    Write-Host "Llack 개발 명령 (윈도우)" -ForegroundColor White
    Write-Host ""
    $rows = @(
        @("setup",       "전체 의존성 설치 (백엔드 + 프론트엔드 + SDK)"),
        @("doctor",      "필요한 도구가 설치되어 있는지 진단"),
        @("seed",        "마이그레이션 + 개발용 시드 데이터"),
        @("dev",         "백엔드 개발 서버 (http://localhost:8000/docs)"),
        @("ui",          "프론트엔드만 브라우저에서 (Tauri 없이)"),
        @("desktop",     "데스크톱 앱 실행 (Tauri)"),
        @("build",       "데스크톱 앱 설치 파일 빌드 (.msi / .exe)"),
        @("example-app", "예제 미니앱을 5180 포트로 서빙"),
        @("test",        "백엔드 + Rust 코어 테스트"),
        @("smoke",       "실행 중인 서버에 대한 종단 검증"),
        @("lint",        "린트 및 타입 검사"),
        @("migrate",     "마이그레이션만 적용"),
        @("reset-db",    "DB 삭제 후 재생성 + 시드"),
        @("clean",       "빌드 산출물 삭제")
    )
    foreach ($row in $rows) {
        Write-Host ("  {0,-14}" -f $row[0]) -ForegroundColor Cyan -NoNewline
        Write-Host $row[1]
    }
    Write-Host ""
    Write-Host "처음이라면: .\llack.ps1 doctor  ->  setup  ->  seed  ->  dev" -ForegroundColor Yellow
    Write-Host ""
}

function Task-Doctor {
    Write-Step "필수 도구 확인"
    $problems = @()

    try {
        $python = Resolve-Python
        $reported = (& $python[0] @($python[1..($python.Length-1)]) --version 2>&1)
        Write-Ok "Python: $reported"
    } catch {
        $problems += "Python 3.11+ : winget install Python.Python.3.12"
    }

    if (Get-Command node -ErrorAction SilentlyContinue) {
        Write-Ok "Node: $(node --version)"
    } else {
        $problems += "Node 20+ : winget install OpenJS.NodeJS.LTS"
    }

    if (Get-Command cargo -ErrorAction SilentlyContinue) {
        Write-Ok "Rust: $(cargo --version)"
    } else {
        $problems += "Rust : winget install Rustlang.Rustup  (설치 후 새 터미널)"
    }

    # Tauri 는 MSVC 링커가 필요합니다. 없으면 cargo build 가 link.exe 오류로 실패합니다.
    $hasLinker = $false
    if (Get-Command link.exe -ErrorAction SilentlyContinue) { $hasLinker = $true }
    else {
        $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
        if (Test-Path $vswhere) {
            $found = & $vswhere -latest -products * `
                -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
                -property installationPath 2>$null
            if ($found) { $hasLinker = $true; Write-Ok "MSVC 빌드 도구: $found" }
        }
    }
    if ($hasLinker) {
        if (-not (Get-Command link.exe -ErrorAction SilentlyContinue)) { } else { Write-Ok "MSVC 링커: 확인" }
    } else {
        $problems += "MSVC C++ 빌드 도구 : winget install Microsoft.VisualStudio.2022.BuildTools --override `"--quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended`""
    }

    # WebView2 는 윈도우 11 과 최신 윈도우 10 에 기본 포함되어 있습니다.
    $webview2 = Get-ItemProperty -ErrorAction SilentlyContinue `
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    if ($webview2) {
        Write-Ok "WebView2 런타임: $($webview2.pv)"
    } else {
        Write-Host "    WebView2 런타임을 레지스트리에서 확인하지 못했습니다." -ForegroundColor Yellow
        Write-Host "    윈도우 11 이면 기본 포함입니다. 문제가 생기면:" -ForegroundColor Yellow
        Write-Host "      winget install Microsoft.EdgeWebView2Runtime" -ForegroundColor Yellow
    }

    Write-Host ""
    if ($problems.Count -eq 0) {
        Write-Host "모두 준비되었습니다. 다음: .\llack.ps1 setup" -ForegroundColor Green
    } else {
        Write-Host "다음 항목이 필요합니다:" -ForegroundColor Red
        foreach ($problem in $problems) { Write-Host "  - $problem" }
        Write-Host ""
        Write-Host "백엔드와 UI 만 확인하려면 Rust/MSVC 없이도 됩니다 (dev, ui, test)." -ForegroundColor Yellow
    }
    Write-Host ""
}

function Task-SetupBackend {
    Write-Step "백엔드 가상환경 및 의존성"
    $python = Resolve-Python
    Invoke-In $Backend {
        if (-not (Test-Path ".venv")) {
            & $python[0] @($python[1..($python.Length-1)]) -m venv .venv
        }
        & $Pip install -q --upgrade pip setuptools wheel
        & $Pip install -q -e ".[dev]"
        & $Pip install -q asgi-lifespan anyio
    }
    Write-Ok "완료"
}

function Task-SetupDesktop {
    Write-Step "데스크톱 프론트엔드 의존성"
    Assert-Tool node "Node" "winget install OpenJS.NodeJS.LTS"
    Invoke-In $Desktop { npm install --no-audit --no-fund }
    Write-Ok "완료"
}

function Task-SetupSdk {
    Write-Step "미니앱 SDK 빌드"
    Invoke-In $Sdk {
        npm install --no-audit --no-fund
        npm run build
    }
    Write-Ok "완료"
}

function Task-Migrate {
    Invoke-In $Backend {
        New-Item -ItemType Directory -Force -Path "var" | Out-Null
        & $Alembic upgrade head
    }
}

function Task-Seed {
    Write-Step "마이그레이션 및 시드"
    Task-Migrate
    Invoke-In $Backend { & $Py -m scripts.seed }
}

function Task-Dev {
    Write-Step "백엔드 개발 서버"
    Task-Migrate
    Write-Ok "http://localhost:8000/docs  (Ctrl+C 로 종료)"
    Invoke-In $Backend {
        & $Uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
    }
}

function Task-Ui {
    Write-Step "프론트엔드 개발 서버"
    Write-Ok "http://localhost:1420"
    Invoke-In $Desktop { npm run dev }
}

function Task-Desktop {
    Write-Step "데스크톱 앱 (Tauri)"
    Assert-Tool cargo "Rust" "winget install Rustlang.Rustup"
    Write-Ok "첫 빌드는 Rust 의존성 컴파일로 5~15분 걸립니다."
    Invoke-In $Desktop { npm run app:dev }
}

function Task-Build {
    Write-Step "데스크톱 설치 파일 빌드"
    Assert-Tool cargo "Rust" "winget install Rustlang.Rustup"
    Invoke-In $Desktop { npm run app:build }
    Write-Ok "산출물: desktop\target\release\bundle\"
}

function Task-ExampleApp {
    Write-Step "예제 미니앱 (http://localhost:5180)"
    $python = Resolve-Python
    Invoke-In (Join-Path $Root "examples\apps\standup") {
        & $python[0] @($python[1..($python.Length-1)]) -m http.server 5180
    }
}

function Task-Test {
    Write-Step "백엔드 테스트"
    Invoke-In $Backend { & $Pytest -q }
    if (Get-Command cargo -ErrorAction SilentlyContinue) {
        Write-Step "Rust 코어 테스트"
        Invoke-In $Desktop { cargo test -p llack-core }
    } else {
        Write-Host "    Rust 가 없어 코어 테스트를 건너뜁니다." -ForegroundColor Yellow
    }
}

function Task-Smoke {
    Write-Step "종단 검증 (서버가 실행 중이어야 합니다)"
    Invoke-In $Backend {
        & $Py scripts\smoke_realtime.py
        & $Py scripts\smoke_apps.py
    }
}

function Task-Lint {
    Write-Step "린트 및 타입 검사"
    Invoke-In $Backend { & $Ruff check app tests scripts }
    Invoke-In $Desktop { npx tsc --noEmit }
    if (Get-Command cargo -ErrorAction SilentlyContinue) {
        Invoke-In $Desktop { cargo clippy -p llack-core -- -D warnings }
    }
    Invoke-In $Sdk { npx tsc -p tsconfig.json --noEmit }
    Write-Ok "완료"
}

function Task-ResetDb {
    Write-Step "개발 DB 초기화"
    Get-ChildItem -Path (Join-Path $Backend "var") -Filter "llack-dev.db*" -ErrorAction SilentlyContinue |
        Remove-Item -Force
    Task-Seed
}

function Task-Clean {
    Write-Step "빌드 산출물 삭제"
    foreach ($path in @(
        (Join-Path $Desktop "dist"),
        (Join-Path $Sdk "dist"),
        (Join-Path $Backend ".pytest_cache"),
        (Join-Path $Backend ".ruff_cache")
    )) {
        if (Test-Path $path) { Remove-Item -Recurse -Force $path }
    }
    Write-Ok "완료"
}

switch ($Task.ToLower()) {
    "help"        { Task-Help }
    "doctor"      { Task-Doctor }
    "setup"       { Task-SetupBackend; Task-SetupDesktop; Task-SetupSdk
                    Write-Host ""
                    Write-Host "설치 완료. 다음: .\llack.ps1 seed" -ForegroundColor Green }
    "setup-backend" { Task-SetupBackend }
    "setup-desktop" { Task-SetupDesktop }
    "setup-sdk"   { Task-SetupSdk }
    "migrate"     { Task-Migrate }
    "seed"        { Task-Seed }
    "dev"         { Task-Dev }
    "ui"          { Task-Ui }
    "desktop"     { Task-Desktop }
    "build"       { Task-Build }
    "example-app" { Task-ExampleApp }
    "test"        { Task-Test }
    "smoke"       { Task-Smoke }
    "lint"        { Task-Lint }
    "reset-db"    { Task-ResetDb }
    "clean"       { Task-Clean }
    default {
        Write-Host "알 수 없는 명령: $Task" -ForegroundColor Red
        Task-Help
        exit 1
    }
}
