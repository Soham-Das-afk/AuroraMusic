param(
  [Parameter(Mandatory=$true)][string]$Tag,
  [Parameter(Mandatory=$false)][string]$NotesFile
)

function Ensure-Gh {
  if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    $paths = @(
      "C:\\Program Files\\GitHub CLI\\gh.exe",
      "$env:LOCALAPPDATA\\Programs\\gh\\bin\\gh.exe"
    )
    foreach ($p in $paths) {
      if (Test-Path $p) {
        $env:PATH = (Split-Path $p) + ";" + $env:PATH
        break
      }
    }
  }
  if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Error "GitHub CLI (gh) not found. Install from https://cli.github.com/ or via winget: winget install GitHub.cli"
    exit 1
  }
}

Ensure-Gh

if (-not $NotesFile) {
  $NotesPath = Join-Path $PSScriptRoot "..\\release-notes\\$Tag.md"
} else {
  $NotesPath = $NotesFile
}

if (-not (Test-Path $NotesPath)) {
  Write-Host "Release notes not found at $NotesPath. Proceeding without notes."
  gh release create $Tag --latest --generate-notes
} else {
  gh release create $Tag --latest --title "AuroraMusic $Tag" --notes-file "$NotesPath"
}
