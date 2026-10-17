' Renders every slide of a PPTX to PNG through PowerPoint (late-bound IDispatch COM) and writes layout findings.
' Usage: cscript //nologo render_deck.vbs <deck.pptx> <outDir> [widthPx] [heightPx]
' Opens read-only without a window, closes only its own presentation, and quits PowerPoint only if it started it
' with nothing else open. Never terminates other PowerPoint sessions.
Option Explicit
Dim deckPath, outDir, wPx, hPx, app, pres, i, slide, shp, findings, sw, sh, fso, f, count, preOpen, bh, nm
deckPath = WScript.Arguments(0)
outDir = WScript.Arguments(1)
wPx = 1920 : hPx = 1080
If WScript.Arguments.Count > 2 Then wPx = CLng(WScript.Arguments(2))
If WScript.Arguments.Count > 3 Then hPx = CLng(WScript.Arguments(3))
Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FolderExists(outDir) Then fso.CreateFolder(outDir)

Set app = CreateObject("PowerPoint.Application")
preOpen = app.Presentations.Count
Set pres = app.Presentations.Open(deckPath, True, False, False)  ' ReadOnly, Untitled=False, WithWindow=False
sw = pres.PageSetup.SlideWidth : sh = pres.PageSetup.SlideHeight
count = pres.Slides.Count
findings = ""
For i = 1 To count
  Set slide = pres.Slides(i)
  slide.Export outDir & "\slide-" & Right("0" & i, 2) & ".png", "PNG", wPx, hPx
  For Each shp In slide.Shapes
    nm = Replace(shp.Name, """", "'")
    If shp.Left < -1 Or shp.Top < -1 Or shp.Left + shp.Width > sw + 1 Or shp.Top + shp.Height > sh + 1 Then
      findings = findings & "{""slide"":" & i & ",""shape"":""" & nm & """,""issue"":""out_of_bounds""},"
    End If
    If shp.HasTextFrame Then
      If shp.TextFrame.HasText Then
        bh = shp.TextFrame.TextRange.BoundHeight
        If bh > shp.Height + 4 Then
          findings = findings & "{""slide"":" & i & ",""shape"":""" & nm & """,""issue"":""text_overflow"",""text_pt"":" & _
            Replace(CStr(Round(bh, 1)), ",", ".") & ",""box_pt"":" & Replace(CStr(Round(shp.Height, 1)), ",", ".") & "},"
        End If
      End If
    End If
  Next
Next
If Len(findings) > 0 Then findings = Left(findings, Len(findings) - 1)
Set f = fso.CreateTextFile(outDir & "\layout-report.json", True)
f.WriteLine "{""deck"":""" & fso.GetFileName(deckPath) & """,""slide_count"":" & count & ",""slide_width_pt"":" & sw & _
  ",""slide_height_pt"":" & sh & ",""wide_16x9"":" & LCase(CStr(Abs(sw / sh - 16 / 9) < 0.01)) & _
  ",""export_px"":""" & wPx & "x" & hPx & """,""renderer"":""Microsoft PowerPoint " & app.Version & " (COM)"",""findings"":[" & findings & "]}"
f.Close
On Error Resume Next
pres.SaveAs Replace(deckPath, ".pptx", ".pdf"), 32
If Err.Number <> 0 Then WScript.Echo "PDF export skipped (" & Err.Description & ")" Else WScript.Echo "exported PDF"
On Error GoTo 0
pres.Close
If preOpen = 0 And app.Presentations.Count = 0 Then app.Quit
WScript.Echo "rendered " & count & " slides (" & sw & "x" & sh & " pt) -> " & outDir
