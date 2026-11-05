# 推送到 GitHub 的三种方式，任选一种跑
# 用法：powershell -ExecutionPolicy Bypass -File push.ps1 <仓库地址>
#   例：.\push.ps1 https://github.com/shui0/qianxia.git

param([Parameter(Mandatory=$true)][string]$Remote)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$exists = git remote 2>$null
if ($exists -contains "origin") {
    git remote set-url origin $Remote
    Write-Host "已更新 origin → $Remote"
} else {
    git remote add origin $Remote
    Write-Host "已添加 origin → $Remote"
}

Write-Host "`n推送中（如果弹认证窗口，登录一次即可）..."
git push -u origin main
Write-Host "`n完成。"
