[CmdletBinding()]
param([switch]$ValidateOnly)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'service-common.ps1')
Invoke-IndependentService -Name order -ValidateOnly:$ValidateOnly
