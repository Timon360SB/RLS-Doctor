param(
    [ValidateSet('ru', 'en')][string]$Language = 'en',
    [switch]$Check,
    [switch]$Stop
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$env:PYTHONUTF8 = '1'
function T([string]$ru, [string]$en) {
    if ($Language -eq 'ru') { return $ru }
    return $en
}

function Add-ToolPath([string]$directory) {
    if (Test-Path -LiteralPath $directory) { $env:PATH = $directory + ';' + $env:PATH }
}
Add-ToolPath (Join-Path $env:USERPROFILE '.local\bin')
Add-ToolPath (Join-Path $env:LOCALAPPDATA 'Programs\nodejs')
Add-ToolPath (Join-Path $env:ProgramFiles 'nodejs')
Add-ToolPath (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin')
Add-ToolPath 'D:\Docker\Desktop\resources\bin'

function Require-Tool([string]$name, [string]$helpUrl) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        throw (T "Не найден $name. Установите: $helpUrl и повторите demo.cmd." "Missing $name. Install from $helpUrl and retry demo.cmd.")
    }
}

try {
    Require-Tool 'uv' 'https://docs.astral.sh/uv/getting-started/installation/'
    Require-Tool 'node' 'https://nodejs.org/en/download'
    Require-Tool 'docker' 'https://docs.docker.com/desktop/setup/install/windows-install/'
    Require-Tool 'npx.cmd' 'https://nodejs.org/en/download'

    $ErrorActionPreference = 'Continue'
    $engine = & docker info --format '{{.OSType}}' 2>$null
    $engineExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($engineExit -ne 0 -or $engine -ne 'linux') { throw (T 'Откройте Docker Desktop, дождитесь Engine running и включите Linux-контейнеры. Затем повторите demo.cmd.' 'Open Docker Desktop, wait for Engine running and enable Linux containers. Then retry demo.cmd.') }

    Write-Host (T 'Проверяю Supabase CLI 2.121.0...' 'Checking Supabase CLI 2.121.0...')
    $cache = (& npm.cmd config get cache | Select-Object -Last 1).Trim()
    $cli = $null
    for ($attempt = 0; $attempt -lt 2; $attempt++) {
        $candidates = Get-ChildItem -Path (Join-Path $cache '_npx\*\node_modules\@supabase\cli-windows-x64\bin\supabase.exe') -ErrorAction SilentlyContinue
        foreach ($candidate in $candidates) {
            $ErrorActionPreference = 'Continue'
            $candidateVersion = & $candidate.FullName --version 2>$null
            $candidateExit = $LASTEXITCODE
            $ErrorActionPreference = 'Stop'
            if ($candidateExit -eq 0 -and $candidateVersion -contains '2.121.0') { $cli = $candidate; break }
        }
        if ($cli) { break }
        if ($attempt -eq 0) {
            Write-Host (T 'Загружаю Supabase CLI. Это требуется только при первом запуске...' 'Downloading Supabase CLI (first run only)...')
            $ErrorActionPreference = 'Continue'
            & npx.cmd --yes supabase@2.121.0 --version *> $null
            $downloadExit = $LASTEXITCODE
            $ErrorActionPreference = 'Stop'
            if ($downloadExit -ne 0) { throw (T 'Не удалось загрузить Supabase CLI. Проверьте интернет и повторите запуск.' 'Supabase CLI download failed. Check internet and retry.') }
        }
    }
    if (-not $cli) { throw (T 'Supabase CLI не найден. Повторите запуск или установите CLI 2.121.0.' 'Supabase CLI not found. Retry or install CLI 2.121.0.') }
    Add-ToolPath $cli.DirectoryName
    if ($Stop) {
        $ErrorActionPreference = 'Continue'
        & $cli.FullName stop --workdir fixtures *> $null
        $stopExit = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        if ($stopExit -ne 0) { throw (T 'Не удалось остановить среду. Проверьте Docker.' 'Could not stop the environment. Check Docker.') }
        Write-Host (T 'Окружение остановлено. Локальные данные сохранены.' 'Environment stopped. Local data preserved.')
        exit 0
    }

    if (-not $Stop) {
        Write-Host (T 'Готовлю зависимости Python...' 'Preparing Python dependencies...')
        & uv sync --project python --python 3.12 --frozen --group dev
        if ($LASTEXITCODE -ne 0) { throw (T 'Не удалось подготовить Python. Проверьте сообщение выше и повторите запуск.' 'Python setup failed. Check the message above and retry.') }
    }
    $arguments = @('run', '--project', 'python', 'python', 'scripts/demo.py', '--language', $Language)
    if ($Check) { $arguments += '--check' }
    if ($Stop) { $arguments += '--stop' }
    & uv @arguments
    exit $LASTEXITCODE
} catch {
    Write-Host ((T 'Подготовка: ' 'Setup: ') + $_.Exception.Message) -ForegroundColor Yellow
    exit 3
}
