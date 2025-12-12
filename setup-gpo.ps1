# Setup GPO voor HR en IT department software deployment
# Run dit script op je management instance met admin privileges
# Vereist: Group Policy Management Tools (GPMC)

param(
    [string]$DomainName = "org.innovatech.com",
    [string]$FirefoxInstallerPath = "C:\Software\Firefox-Setup.msi",
    [string]$PuttyInstallerPath = "C:\Software\putty-64bit.msi"
)

# Importeer modules
Import-Module GroupPolicy
Import-Module ActiveDirectory

Write-Host "=========================================="
Write-Host "GPO Setup for HR (Firefox) and IT (Putty)"
Write-Host "=========================================="
Write-Host ""

# Controleer of scripts as admin draaien
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERROR: Script moet als Administrator draaien!" -ForegroundColor Red
    exit 1
}

# ============================================
# STAP 1: Create GPO for HR - Firefox Deployment
# ============================================

Write-Host "[STAP 1] GPO aanmaken voor HR (Firefox deployment)..." -ForegroundColor Green

try {
    $gpoHR = New-GPO -Name "Deploy-Firefox-HR" -Comment "Deployment van Firefox voor HR department"
    Write-Host "✓ GPO 'Deploy-Firefox-HR' aangemaakt" -ForegroundColor Green
} catch {
    Write-Host "⚠ GPO 'Deploy-Firefox-HR' bestaat mogelijk al" -ForegroundColor Yellow
    $gpoHR = Get-GPO -Name "Deploy-Firefox-HR"
}

# Link GPO to Dept-HR security group
$depthRDN = "CN=Dept-HR,OU=Users,OU=innovatech,DC=org,DC=innovatech,DC=com"
try {
    $gpoHR | New-GPLink -Target "OU=Users,OU=innovatech,DC=org,DC=innovatech,DC=com" -LinkEnabled Yes
    Write-Host "✓ GPO gelinkt aan Users OU" -ForegroundColor Green
} catch {
    Write-Host "⚠ Linking faalde (mogelijk al gelinkt)" -ForegroundColor Yellow
}

# Configure Firefox installation via Group Policy
# Dit doen we via Registry policy voor software installation
Write-Host ""
Write-Host "Configureer Firefox installatie:"
Write-Host "1. Open Group Policy Editor: gpmc.msc"
Write-Host "2. Bewerk 'Deploy-Firefox-HR' policy"
Write-Host "3. Ga naar: Computer Configuration → Policies → Software Settings → Software Installation"
Write-Host "4. Right-click → New → Package"
Write-Host "5. Selecteer Firefox MSI installer"
Write-Host "6. Kies 'Assigned' als deployment method"
Write-Host ""

# ============================================
# STAP 2: Create GPO for IT - Putty Deployment
# ============================================

Write-Host "[STAP 2] GPO aanmaken voor IT (Putty deployment)..." -ForegroundColor Green

try {
    $gpoIT = New-GPO -Name "Deploy-Putty-IT" -Comment "Deployment van Putty voor IT department"
    Write-Host "✓ GPO 'Deploy-Putty-IT' aangemaakt" -ForegroundColor Green
} catch {
    Write-Host "⚠ GPO 'Deploy-Putty-IT' bestaat mogelijk al" -ForegroundColor Yellow
    $gpoIT = Get-GPO -Name "Deploy-Putty-IT"
}

# Link GPO to Dept-IT security group
try {
    $gpoIT | New-GPLink -Target "OU=Users,OU=innovatech,DC=org,DC=innovatech,DC=com" -LinkEnabled Yes
    Write-Host "✓ GPO gelinkt aan Users OU" -ForegroundColor Green
} catch {
    Write-Host "⚠ Linking faalde (mogelijk al gelinkt)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Configureer Putty installatie:"
Write-Host "1. Open Group Policy Editor: gpmc.msc"
Write-Host "2. Bewerk 'Deploy-Putty-IT' policy"
Write-Host "3. Ga naar: Computer Configuration → Policies → Software Settings → Software Installation"
Write-Host "4. Right-click → New → Package"
Write-Host "5. Selecteer Putty MSI installer"
Write-Host "6. Kies 'Assigned' als deployment method"
Write-Host ""

# ============================================
# STAP 3: Alternative - Software via Startup Script
# ============================================

Write-Host "[STAP 3] Alternative: Software installation via Startup Script..." -ForegroundColor Green
Write-Host ""

# Create a custom startup script dat applicaties installeert op basis van AD group membership
$startupScriptContent = @'
@echo off
REM Check if user is member of Dept-HR
gpresult /h /scope:user /f "%TEMP%\gpreport.html"
findstr /C:"Dept-HR" "%TEMP%\gpreport.html" >nul
if %ERRORLEVEL% EQU 0 (
    echo Installing Firefox for HR user...
    msiexec /i "\\servername\Software\Firefox-Setup.msi" /quiet /norestart
)

REM Check if computer is member of Dept-IT
findstr /C:"Dept-IT" "%TEMP%\gpreport.html" >nul
if %ERRORLEVEL% EQU 0 (
    echo Installing Putty for IT user...
    msiexec /i "\\servername\Software\putty-64bit.msi" /quiet /norestart
)
'@

Write-Host "Als alternatief kun je een startup-script gebruiken:"
Write-Host "1. Maak map aan: \\$DomainName\sysvol\$DomainName\Policies\{GUID}\User\Scripts\Logon"
Write-Host "2. Plaats batch-script daar"
Write-Host "3. Link script in Group Policy"
Write-Host ""

# ============================================
# Summary
# ============================================

Write-Host "=========================================="
Write-Host "GPO Setup Voltooid!" -ForegroundColor Green
Write-Host "=========================================="
Write-Host ""
Write-Host "Volgende stappen:"
Write-Host "1. Zorg dat Firefox en Putty MSI installers beschikbaar zijn:"
Write-Host "   - Firefox: $FirefoxInstallerPath"
Write-Host "   - Putty: $PuttyInstallerPath"
Write-Host ""
Write-Host "2. Open gpmc.msc en configureer de MSI packages in elke GPO"
Write-Host ""
Write-Host "3. Run gpupdate /force op client machines"
Write-Host ""
Write-Host "4. Test met nieuwe users:"
Write-Host "   - Voeg HR-user toe → Firefox wordt geïnstalleerd"
Write-Host "   - Voeg IT-user toe → Putty wordt geïnstalleerd"
Write-Host ""

Write-Host "GPO's aangemaakt:"
Get-GPO -Name "Deploy-Firefox-HR" | Select-Object DisplayName, Owner
Get-GPO -Name "Deploy-Putty-IT" | Select-Object DisplayName, Owner
