param(
  [string]$Deck = (Join-Path $PSScriptRoot "ScopeGuard_Pitch.pptx"),
  [string]$OutDir = (Join-Path $PSScriptRoot "qa"),
  [int]$Width = 1920,
  [int]$Height = 1080
)
# Renders every slide of $Deck to PNG through PowerPoint COM.
# Opens read-only without a window; closes only its own presentation; never kills PowerPoint.
$ErrorActionPreference = "Stop"
$Deck = (Resolve-Path $Deck).Path
New-Item -ItemType Directory -Force $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path
$app = $null; $pres = $null
try {
  trap { Write-Error $_; throw }
  $app = New-Object -ComObject PowerPoint.Application
  # Open(FileName, ReadOnly, Untitled, WithWindow)
  $pres = $app.Presentations.Open($Deck, -1, 0, 0)
  $count = $pres.Slides.Count
  $w = $pres.PageSetup.SlideWidth; $h = $pres.PageSetup.SlideHeight
  $findings = @()
  for ($i = 1; $i -le $count; $i++) {
    $slide = $pres.Slides.Item($i)
    $name = "slide-{0:D2}.png" -f $i
    $slide.Export((Join-Path $OutDir $name), "PNG", $Width, $Height)
    foreach ($shape in $slide.Shapes) {
      $l = $shape.Left; $t = $shape.Top; $r = $l + $shape.Width; $b = $t + $shape.Height
      if ($l -lt -1 -or $t -lt -1 -or $r -gt ($w + 1) -or $b -gt ($h + 1)) {
        $findings += [ordered]@{ slide = $i; shape = $shape.Name; issue = "out_of_bounds" }
      }
      if ($shape.HasTextFrame -and $shape.TextFrame.HasText) {
        $tf = $shape.TextFrame2
        $bh = $shape.TextFrame.TextRange.BoundHeight
        if ($bh -gt ($shape.Height + 2) -and $tf.AutoSize -eq 0) {
          $findings += [ordered]@{ slide = $i; shape = $shape.Name; issue = "text_overflow"; text_height = [math]::Round($bh,1); box_height = [math]::Round($shape.Height,1) }
        }
      }
    }
  }
  $report = [ordered]@{
    deck = (Split-Path $Deck -Leaf)
    slide_count = $count
    slide_width_pt = $w
    slide_height_pt = $h
    wide_16x9 = ([math]::Abs(($w / $h) - (16 / 9)) -lt 0.01)
    export_px = "$Width x $Height"
    findings = $findings
  }
  $report | ConvertTo-Json -Depth 5 | Out-File -Encoding utf8 (Join-Path $OutDir "layout-report.json")
  Write-Output ("rendered {0} slides; {1} layout findings" -f $count, $findings.Count)
}
finally {
  if ($pres -ne $null) { $pres.Close(); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($pres) }
  if ($app -ne $null) {
    try { if ($app.Presentations.Count -eq 0) { $app.Quit() } } catch { Write-Warning "PowerPoint left running (could not query/quit cleanly)" }
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($app)
  }
  [GC]::Collect(); [GC]::WaitForPendingFinalizers()
}
