# Remove ARIA do startup do Windows
$StartupDir   = [System.Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "ARIA.lnk"
if (Test-Path $ShortcutPath) {
    Remove-Item $ShortcutPath -Force
    Write-Host "ARIA removida do startup." -ForegroundColor Yellow
} else {
    Write-Host "ARIA nao estava no startup." -ForegroundColor Gray
}
