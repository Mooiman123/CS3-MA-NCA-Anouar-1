# Controleer AD-user en RDP rechten op Windows EC2
# Sla dit script op als check-ad-user.ps1 en voer uit als admin op de instance

param(
    [string]$UserName = "test1",
    [string]$Domain = "org.innovatech.com"
)

Write-Host "--- AD User Info ---"
Get-ADUser -Identity $UserName -Properties Enabled,PasswordLastSet | Format-List

Write-Host "--- Groepen ---"
Get-ADUser -Identity $UserName | Get-ADPrincipalGroupMembership | Select Name

Write-Host "--- Lid van Remote Desktop Users? ---"
$rdpGroup = Get-ADGroupMember -Identity "Remote Desktop Users" | Where-Object { $_.SamAccountName -eq $UserName }
if ($rdpGroup) {
    Write-Host "$UserName is lid van Remote Desktop Users"
} else {
    Write-Host "$UserName is NIET lid van Remote Desktop Users"
}

Write-Host "--- Domain Join Status ---"
$domain = (Get-WmiObject Win32_ComputerSystem).Domain
if ($domain -eq $Domain) {
    Write-Host "Instance is joined aan domein: $Domain"
} else {
    Write-Host "Instance is NIET joined aan domein: $Domain (huidig: $domain)"
}

Write-Host "--- RDP Policy ---"
$rdpPolicy = Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server" -Name fDenyTSConnections
if ($rdpPolicy.fDenyTSConnections -eq 0) {
    Write-Host "RDP is ENABLED op deze instance"
} else {
    Write-Host "RDP is NIET enabled op deze instance"
}
