param(
  [string]$Deck = (Join-Path $PSScriptRoot "ScopeGuard_Pitch.pptx"),
  [string]$OutDir = (Join-Path $PSScriptRoot "qa"),
  [int]$Width = 1920,
  [int]$Height = 1080
)
# Renders every slide to PNG through installed PowerPoint. The typed PowerShell interop fails on the build
# machine (TYPE_E_ELEMENTNOTFOUND), so this delegates to a late-bound VBScript renderer (render_deck.vbs).
$ErrorActionPreference = "Stop"
$Deck = (Resolve-Path $Deck).Path
New-Item -ItemType Directory -Force $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path
Get-ChildItem $OutDir -Filter "slide-*.png" -ErrorAction SilentlyContinue | Remove-Item -Force
& cscript.exe //nologo (Join-Path $PSScriptRoot "render_deck.vbs") $Deck $OutDir $Width $Height
if ($LASTEXITCODE -ne 0) { throw "PowerPoint rendering failed" }
