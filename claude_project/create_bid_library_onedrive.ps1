# Creates the "KEYES - Bid library" folder structure in your synced OneDrive for Business
# (e.g. "OneDrive - NRB") and copies the bid fact sheet template into folder 01.
#
# Usage (PowerShell, in the folder containing this script):
#   powershell -ExecutionPolicy Bypass -File .\create_bid_library_onedrive.ps1
#   powershell -ExecutionPolicy Bypass -File .\create_bid_library_onedrive.ps1 -Root "D:\OneDrive - NRB"
#
# Safe to run more than once: existing folders and files are left untouched.

param(
    [string]$Root = $env:OneDriveCommercial
)

if (-not $Root) { $Root = $env:OneDrive }
if (-not $Root -or -not (Test-Path $Root)) {
    Write-Error "OneDrive folder not found. Pass it explicitly: -Root 'C:\Users\<you>\OneDrive - NRB'"
    exit 1
}

$Library = Join-Path $Root "KEYES - Bid library"
$Folders = @(
    "01 Fact sheet & standard texts",
    "02 Corporate presentation",
    "03 Portfolio - products & services",
    "04 Certifications & attestations",
    "05 Financials",
    "06 References & satisfaction forms",
    "07 CVs & team profiles",
    "08 Partnerships & vendor letters",
    "09 Templates (ESPD-DUME, NDA, cover letters)",
    "10 Past offers (won & lost)",
    "20 Tenders - active",
    "21 Tenders - archive"
)
$TenderTemplate = Join-Path $Library "20 Tenders - active\_TEMPLATE - Buyer - Reference - Title"
$TenderFolders = @(
    "01 Tender documents & annexes",
    "02 Buyer Q&A & corrections",
    "03 Analysis & go-no-go",
    "04 Offer drafts",
    "05 Pricing",
    "06 Submitted offer"
)

$created = 0
function Ensure-Folder([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
        $script:created++
        Write-Host "  + $Path"
    }
}

Write-Host "Bid library: $Library"
Ensure-Folder $Library
foreach ($f in $Folders) { Ensure-Folder (Join-Path $Library $f) }
Ensure-Folder $TenderTemplate
foreach ($f in $TenderFolders) { Ensure-Folder (Join-Path $TenderTemplate $f) }

$Template = Join-Path $PSScriptRoot "KEYES_Bid_Fact_Sheet_Template.docx"
$Target = Join-Path $Library "01 Fact sheet & standard texts\KEYES_Bid_Fact_Sheet_Template.docx"
if ((Test-Path -LiteralPath $Template) -and -not (Test-Path -LiteralPath $Target)) {
    Copy-Item -LiteralPath $Template -Destination $Target
    Write-Host "  + $Target"
}

Write-Host "Done: $created folder(s) created. OneDrive will sync them to the cloud automatically."
