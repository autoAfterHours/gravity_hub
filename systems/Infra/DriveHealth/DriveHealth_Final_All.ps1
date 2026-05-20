# =========================
# DRIVE HEALTH CHECK
# Scoped execution: All Environments, single Environment, single Site, or single Server
# Scope is controlled via env vars (Orbit) or an interactive menu (standalone).
# =========================

Clear-Host

# =========================
# CONFIG
# =========================

$lowSpaceThreshold = 15

# =========================
# STATIC SERVER INVENTORY
# =========================

$QA_INVENTORY = @{
    "CER_QA" = @{
        Domain  = "hcaqa.corpadqa.net"
        Servers = @("XRDCWQAPPCAC10B","XRDCWQDBSCAC10B","XRDCWQINTCAC10B","XRDCWQRPTCAC10B","XRDCWQWEBCAC10B")
    }
    "ENT_QA" = @{
        Domain  = "hcaqa.corpadqa.net"
        Servers = @("XRDCWQAPPCAC08B","XRDCWQDBSCAC08B","XRDCWQINTCAC08B","XRDCWQRPTCAC08B","XRDCWQWEBCAC08B")
    }
    "MTX_QA" = @{
        Domain  = "hcaqa.corpadqa.net"
        Servers = @("XRDCWQAPPCAC20B","XRDCWQDBSCAC20B","XRDCWQINTCAC20B","XRDCWQRPTCAC20B","XRDCWQWEBCAC20B")
    }
}

$SITE_SUFFIX_MAP = @{
    "CER"="10B"; "CSA"="20B"; "CWT"="22B"; "DAL"="02B"; "EFD"="23B"
    "GCD"="24B"; "HOU"="03B"; "NAS"="07B"; "NFD"="21B"; "OPK"="04B"
    "RIC"="03B"; "SAN"="01B"; "TAM"="06B"; "TSD"="25B"; "TRN"="00B"
}

$FWD_SITES = @("CWT","DAL","HOU","GCD","SAN")

# =========================
# SCOPE RESOLUTION
# =========================

$orbitEnvs   = $env:ORBIT_DH_ENVS    # "QA", "PreProd", "Prod", or "QA,PreProd,Prod"
$orbitSite   = $env:ORBIT_DH_SITE    # e.g. "CER_QA" or "CSA" — optional
$orbitServer = $env:ORBIT_DH_SERVER  # specific machine name — optional

if (-not $orbitEnvs) {
    Write-Host "Select scope:" -ForegroundColor Cyan
    Write-Host "1 = QA only"
    Write-Host "2 = Pre-Prod only"
    Write-Host "3 = Production only"
    Write-Host "4 = All Environments"
    $choice = Read-Host "Enter choice"
    switch ($choice) {
        "1" { $orbitEnvs = "QA" }
        "2" { $orbitEnvs = "PreProd" }
        "3" { $orbitEnvs = "Prod" }
        "4" { $orbitEnvs = "QA,PreProd,Prod" }
        default { Write-Host "Invalid selection." -ForegroundColor Red; exit 1 }
    }
}

$selectedEnvs = $orbitEnvs -split ","

# =========================
# CREDENTIAL ACQUISITION
# =========================
# QA uses the current Windows session.
# Pre-Prod and Prod share one stored credential for hca.corpad.net.
# The same super account covers all environments.

$credMap = @{}

if ($selectedEnvs -contains "QA") {
    $credMap["QA"] = $null
}

$needsHcaCred = ($selectedEnvs -contains "PreProd") -or ($selectedEnvs -contains "Prod")

if ($needsHcaCred) {
    $credStore = "$env:APPDATA\OrbitHub\cred_hca.xml"

    if (Test-Path $credStore) {
        $hcaCred = Import-Clixml -Path $credStore
        Write-Host "Using saved HCA credentials ($($hcaCred.UserName))" -ForegroundColor Green
    } else {
        $hcaCred = Get-Credential -Message "Credentials for Pre-Prod/Prod access on hca.corpad.net"
        if (-not $hcaCred) { Write-Host "No credentials provided." -ForegroundColor Red; exit 1 }
        New-Item -ItemType Directory -Force -Path (Split-Path $credStore) | Out-Null
        $hcaCred | Export-Clixml -Path $credStore
        Write-Host "Credentials saved (encrypted) for future runs." -ForegroundColor Green
    }

    if ($selectedEnvs -contains "PreProd") { $credMap["PreProd"] = $hcaCred }
    if ($selectedEnvs -contains "Prod")    { $credMap["Prod"]    = $hcaCred }
}

# =========================
# BUILD TARGET LIST
# =========================

$targets = [System.Collections.Generic.List[hashtable]]::new()

function Add-Targets {
    param($envName, $domain, $siteName, $servers, $cred)
    foreach ($srv in $servers) {
        if ($orbitServer -and $srv -ne $orbitServer) { continue }
        $script:targets.Add(@{
            Env        = $envName
            Site       = $siteName
            Server     = $srv
            Domain     = $domain
            Credential = $cred
        })
    }
}

foreach ($envName in $selectedEnvs) {

    if ($envName -eq "QA") {
        foreach ($siteKey in $QA_INVENTORY.Keys) {
            if ($orbitSite -and $siteKey -ne $orbitSite) { continue }
            Add-Targets $envName $QA_INVENTORY[$siteKey].Domain $siteKey `
                $QA_INVENTORY[$siteKey].Servers $credMap["QA"]
        }
    }

    elseif ($envName -in @("PreProd","Prod")) {
        $envCode     = if ($envName -eq "PreProd") { "WT" } else { "WP" }
        $siteMapCopy = $SITE_SUFFIX_MAP.Clone()
        if ($envName -eq "Prod") { $siteMapCopy.Remove("TRN") }

        foreach ($site in $siteMapCopy.Keys) {
            if ($orbitSite -and $site -ne $orbitSite) { continue }
            $suffix = $siteMapCopy[$site]
            $px     = if ($site -in $FWD_SITES) { "FWDCW$envCode" } else { "XRDCW$envCode" }
            $servers = @(
                "${px}APPCAC${suffix}", "${px}DBSCAC${suffix}",
                "${px}INTCAC${suffix}", "${px}RPTCAC${suffix}",
                "${px}WEBCAC${suffix}"
            )
            Add-Targets $envName "hca.corpad.net" $site $servers $credMap[$envName]
        }
    }
}

if ($targets.Count -eq 0) {
    Write-Host "No targets matched the specified scope. Check ORBIT_DH_ENVS / ORBIT_DH_SITE / ORBIT_DH_SERVER." -ForegroundColor Red
    exit 1
}

# =========================
# RUN HEADER
# =========================

$scopeLabel = $orbitEnvs
if ($orbitSite)   { $scopeLabel += " / $orbitSite" }
if ($orbitServer) { $scopeLabel += " / $orbitServer" }

$scanStart = Get-Date

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " DRIVE HEALTH CHECK" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ("  Scope   : {0}" -f $scopeLabel)
Write-Host ("  Servers : {0}" -f $targets.Count)
Write-Host ("  Started : {0}" -f $scanStart.ToString("yyyy-MM-dd HH:mm:ss"))
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# =========================
# EXECUTION
# =========================

$results = @()
$idx     = 0

foreach ($t in $targets) {

    $idx++

    $serverType = switch -Regex ($t.Server) {
        "APPCAC" { "APP";       break }
        "DBSCAC" { "DB";        break }
        "WEBCAC" { "WEB";       break }
        "RPTCAC" { "REPORT";    break }
        "INTCAC" { "INTERFACE"; break }
        default  { "UNKNOWN" }
    }

    Write-Host ("  [{0,3}/{1}] {2,-8} {3,-5} {4,-10} — {5}..." -f `
        $idx, $targets.Count, $t.Env, $t.Site, $serverType, $t.Server) -ForegroundColor Cyan

    try {
        $invokeParams = @{
            ComputerName = "$($t.Server).$($t.Domain)"
            ScriptBlock  = {
                Get-Volume | Where-Object {$_.DriveType -eq 'Fixed'} | Select-Object `
                    @{n="Server";e={$env:COMPUTERNAME}},
                    @{n="Drive";e={$_.DriveLetter}},
                    @{n="Label";e={$_.FileSystemLabel}},
                    @{n="FileSystem";e={$_.FileSystem}},
                    @{n="DriveType";e={$_.DriveType}},
                    @{n="HealthStatus";e={$_.HealthStatus}},
                    @{n="OperationalStatus";e={($_.OperationalStatus -join ", ")}},
                    @{n="SizeGB";e={[math]::Round($_.Size/1GB,2)}},
                    @{n="FreeGB";e={[math]::Round($_.SizeRemaining/1GB,2)}},
                    @{n="PercentFree";e={[math]::Round(($_.SizeRemaining/$_.Size)*100,2)}}
            }
        }
        if ($t.Credential) { $invokeParams['Credential'] = $t.Credential }

        $data = Invoke-Command @invokeParams

        foreach ($row in $data) {
            $row | Add-Member -NotePropertyName Env        -NotePropertyValue $t.Env        -Force
            $row | Add-Member -NotePropertyName Site       -NotePropertyValue $t.Site       -Force
            $row | Add-Member -NotePropertyName ServerType -NotePropertyValue $serverType   -Force
            $results += $row
        }

        Write-Host "  ✔ Success" -ForegroundColor Green

    } catch {
        Write-Host "  ✖ Failed — $($_.Exception.Message)" -ForegroundColor Red

        $results += [PSCustomObject]@{
            Server            = $t.Server
            Drive             = $null
            Label             = $null
            FileSystem        = $null
            DriveType         = $null
            HealthStatus      = "UNREACHABLE"
            OperationalStatus = $_.Exception.Message
            SizeGB            = $null
            FreeGB            = $null
            PercentFree       = $null
            Env               = $t.Env
            Site              = $t.Site
            ServerType        = $serverType
        }
    }

    Start-Sleep -Seconds 1
}

# =========================
# FLAGS
# =========================

$elapsed = [math]::Round(((Get-Date) - $scanStart).TotalSeconds)
Write-Host ""
Write-Host ("Scan complete — {0} servers checked in {1}s. Analyzing results..." -f $targets.Count, $elapsed) -ForegroundColor Cyan

$results = $results | Select-Object *, @{
    Name="StatusFlag"; Expression={
        if ($_.HealthStatus -eq "UNREACHABLE")     { "🚨 UNREACHABLE" }
        elseif ($_.HealthStatus -ne "Healthy")     { "🚨 HEALTH" }
        elseif ($_.OperationalStatus -notlike "*OK*") { "⚠️ OPERATION" }
        elseif ($_.PercentFree -lt $lowSpaceThreshold) { "⚠️ LOW SPACE" }
        else { "OK" }
    }
}

# =========================
# OUTPUT TABLE
# =========================

Write-Host ""
Write-Host "----------------------------------------" -ForegroundColor DarkGray
Write-Host ("  {0,-8} {1,-5} {2,-10} {3,-20} {4,-2} {5,6}   {6,6}   {7,6}  {8}" -f `
    "ENV","SITE","TYPE","SERVER","DRV","SIZE","FREE","%FREE","STATUS") -ForegroundColor DarkGray
Write-Host "----------------------------------------" -ForegroundColor DarkGray

foreach ($r in $results) {
    $color = switch -Wildcard ($r.StatusFlag) {
        "🚨*"  { "Red" }
        "⚠️*"  { "Yellow" }
        default { "Green" }
    }
    Write-Host ("{0,-8} {1,-5} {2,-10} {3,-20} {4,-2} {5,6}GB {6,6}GB {7,6}% {8}" -f `
        $r.Env, $r.Site, $r.ServerType, $r.Server, $r.Drive, `
        $r.SizeGB, $r.FreeGB, $r.PercentFree, $r.StatusFlag) -ForegroundColor $color
}

# =========================
# SUMMARY
# =========================

$totalServers   = ($results | Select-Object -ExpandProperty Server -Unique).Count
$countOK        = ($results | Where-Object { $_.StatusFlag -eq "OK" }).Count
$countLowSpace  = ($results | Where-Object { $_.StatusFlag -eq "⚠️ LOW SPACE" }).Count
$countOperation = ($results | Where-Object { $_.StatusFlag -eq "⚠️ OPERATION" }).Count
$countHealth    = ($results | Where-Object { $_.StatusFlag -eq "🚨 HEALTH" }).Count
$countUnreach   = ($results | Where-Object { $_.StatusFlag -eq "🚨 UNREACHABLE" }).Count

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " DRIVE HEALTH SUMMARY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ("  Scope           : {0}" -f $scopeLabel)
Write-Host ("  Servers checked : {0}" -f $totalServers)
Write-Host ("  Drives OK       : {0}" -f $countOK) -ForegroundColor Green
if ($countLowSpace  -gt 0) { Write-Host ("  Low Space       : {0}" -f $countLowSpace)  -ForegroundColor Yellow }
if ($countOperation -gt 0) { Write-Host ("  Op. Warning     : {0}" -f $countOperation) -ForegroundColor Yellow }
if ($countHealth    -gt 0) { Write-Host ("  Health Critical : {0}" -f $countHealth)    -ForegroundColor Red    }
if ($countUnreach   -gt 0) { Write-Host ("  Unreachable     : {0}" -f $countUnreach)   -ForegroundColor Red    }
Write-Host "========================================" -ForegroundColor Cyan

# =========================
# EXPORT
# =========================

$ts = Get-Date -Format "yyyyMMdd_HHmmss"

if ($orbitServer) {
    $scope = "$($selectedEnvs -join '-')_${orbitSite}_${orbitServer}"
} elseif ($orbitSite) {
    $scope = "$($selectedEnvs -join '-')_${orbitSite}"
} elseif ($selectedEnvs.Count -eq 1) {
    $scope = $selectedEnvs[0]
} else {
    $scope = "All"
}

$exportDir = if ($env:ORBIT_LOG_DIR) { $env:ORBIT_LOG_DIR } else { [Environment]::GetFolderPath("Desktop") }
$path = Join-Path $exportDir ("DriveHealth_${scope}_${ts}.csv")

Write-Host ""
Write-Host "Generating report..." -ForegroundColor Cyan
$results | Export-Csv $path -NoTypeInformation
Write-Host "Saved: $path" -ForegroundColor Green

# Auto-open in Excel only when running standalone (not inside Orbit)
if (-not $env:ORBIT_LOG_DIR) { Invoke-Item $path }
