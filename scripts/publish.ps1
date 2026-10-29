# Publishes the source-only bootstrap to a new GitHub repo, after explicit choice.
# Does NOT compile, delete existing projects or upload user videos/API keys.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
function CmdPath($name, $candidates) {
  $command = Get-Command $name -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }
  foreach ($path in $candidates) { if (Test-Path -LiteralPath $path) { return $path } }
  throw "$name not installed. Install Git and GitHub CLI, then run PUBLISH_TO_GITHUB.cmd again. See README.md."
}
$git = CmdPath 'git.exe' @('C:\Program Files\Git\cmd\git.exe','C:\Program Files\Git\bin\git.exe')
$gh = CmdPath 'gh.exe' @('C:\Program Files\GitHub CLI\gh.exe')
Write-Host 'GitHub authentication: a browser page may open.' -ForegroundColor Cyan
& $gh auth status 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
  & $gh auth login --web --git-protocol https
  if ($LASTEXITCODE -ne 0) { throw 'GitHub authentication failed' }
}
Write-Host ''
Write-Host 'The repository stores LMK code and a Windows build workflow, not videos or API keys.'
$choice = Read-Host 'Choose visibility: [1] PRIVATE (default), [2] PUBLIC'
$visibility = if ($choice -eq '2') { '--public' } else { '--private' }
$repo = Read-Host 'GitHub repository name (Enter = LMK-Concat-Studio)'
if (-not $repo) { $repo = 'LMK-Concat-Studio' }
if ($repo -notmatch '^[a-zA-Z0-9._-]+$') { throw 'Invalid repository name' }
$answer = Read-Host "Create and upload $repo ($visibility) to your GitHub account? Type YES to confirm"
if ($answer -ne 'YES') { throw 'Cancelled by user before creating any repository' }
if (Test-Path -LiteralPath '.git') { throw 'This folder is already a Git repository. No automatic force push is allowed.' }
& $git init -b main
if ($LASTEXITCODE -ne 0) { throw 'git init failed' }
& $git add .
if ($LASTEXITCODE -ne 0) { throw 'git add failed' }
& $git -c 'user.name=LMK Source Bootstrap' -c 'user.email=lmk-bootstrap@users.noreply.github.com' commit -m 'Initial LMK native fork and Windows CI workflow'
if ($LASTEXITCODE -ne 0) { throw 'git commit failed' }
& $gh repo create $repo $visibility --source . --remote origin --push
if ($LASTEXITCODE -ne 0) { throw 'GitHub repository creation/push failed; inspect errors above' }
Write-Host 'Uploaded successfully. GitHub Actions will run automatically on main.' -ForegroundColor Green
