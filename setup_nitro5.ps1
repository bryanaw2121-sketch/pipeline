# Setup do motor no Nitro 5. Rode uma vez, no PowerShell.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "`n=== 1. ffmpeg + yt-dlp ===" -ForegroundColor Cyan
if (Get-Command winget -ErrorAction SilentlyContinue) {
    foreach ($p in @("Gyan.FFmpeg", "yt-dlp.yt-dlp")) {
        Write-Host "instalando $p..."
        winget install --id $p -e --accept-source-agreements --accept-package-agreements
    }
} else {
    Write-Host "winget ausente. Instale manualmente:" -ForegroundColor Yellow
    Write-Host "  ffmpeg: https://www.gyan.dev/ffmpeg/builds/  (adicione a pasta bin ao PATH)"
    Write-Host "  yt-dlp: https://github.com/yt-dlp/yt-dlp/releases"
}

Write-Host "`n=== 2. dependencias Python ===" -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Write-Host "`n=== 3. chaves ===" -ForegroundColor Cyan
if (-not (Test-Path ".env")) {
    Copy-Item ".env.sample" ".env"
    Write-Host "criado .env - PREENCHA suas chaves Gemini e Groq" -ForegroundColor Yellow
} else {
    Write-Host ".env ja existe, mantido"
}

Write-Host "`n=== 4. verificacao ===" -ForegroundColor Cyan
foreach ($c in @("ffmpeg", "ffprobe", "yt-dlp", "python")) {
    $g = Get-Command $c -ErrorAction SilentlyContinue
    if ($g) { Write-Host "  OK   $c" -ForegroundColor Green }
    else    { Write-Host "  FALTA $c (reabra o terminal p/ atualizar o PATH)" -ForegroundColor Red }
}

if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    Write-Host "`n  GPU detectada (NVENC sera usado no render):" -ForegroundColor Green
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
} else {
    Write-Host "`n  Sem GPU NVIDIA - render pela CPU (mais lento, funciona igual)" -ForegroundColor Yellow
}

Write-Host "`nPronto. Teste com um video curto primeiro:" -ForegroundColor Cyan
Write-Host '  python main.py --url "SEU_LINK" --qtd 3' -ForegroundColor White
