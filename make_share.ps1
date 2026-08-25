# -*- coding: utf-8 -*-
# ============================================================
#  MorningBoard 打包分享版
#  双击运行（或 powershell -ExecutionPolicy Bypass -File make_share.ps1）
#  生成的 zip 不含个人缓存(cache/)与字节码(__pycache__)，可直接发给朋友。
#  朋友收到后：解压 -> 双击 一键安装.bat 即可。
# ============================================================
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path   # MorningBoard_Share
$parent = Split-Path -Parent $root                        # 工作区根目录
$out = Join-Path $parent "MorningBoard_分享版_一键安装.zip"

$skipDirs = @("cache", "__pycache__")
$skipExts = @(".pyc", ".zip", ".log", ".pyo", ".lnk")

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
if (Test-Path $out) { Remove-Item $out -Force }
$zip = [System.IO.Compression.ZipFile]::Open($out, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    $count = 0
    $files = Get-ChildItem -Path $root -Recurse -File -Force
    foreach ($f in $files) {
        $rel = "MorningBoard_Share\" + $f.FullName.Substring($root.Length + 1)      # 如 MorningBoard_Share/app/gui.py
        $top = $f.FullName.Substring($root.Length + 1).Split([char]'\')[0]
        if ($skipDirs -contains $top) { continue }
        if ($skipDirs -contains $f.Directory.Name) { continue }
        if ($skipExts -contains $f.Extension.ToLower()) { continue }
        $null = [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $f.FullName, $rel, [System.IO.Compression.CompressionLevel]::Optimal)
        $count++
    }
    Write-Host ("已打包 {0} 个文件" -f $count)
} finally {
    $zip.Dispose()
}
Write-Host ("生成分享包：{0}（{1} KB）" -f $out, [math]::Round((Get-Item $out).Length / 1KB, 1))
Write-Host "发给朋友，对方解压后双击『一键安装.bat』即可自动装好。"
