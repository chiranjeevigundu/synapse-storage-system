param(
    [string]$EndpointUri = "http://192.168.12.37/ingest/upload",
    [string]$ApiKey = "super_secret_homelab_key"
)

$ErrorActionPreference = "Stop"

$SourceDevice = $env:COMPUTERNAME
$BaseFolder = "C:\NAS_Outbox"
$SentFolder = "$BaseFolder\Sent"

if (!(Test-Path $BaseFolder)) { New-Item -ItemType Directory -Force -Path $BaseFolder | Out-Null }
if (!(Test-Path $SentFolder)) { New-Item -ItemType Directory -Force -Path $SentFolder | Out-Null }

Write-Host "Windows Sentinel Agent Initialized."
Write-Host "Device: $SourceDevice"
Write-Host "Monitoring: $BaseFolder"
Write-Host "Endpoint: $EndpointUri"

while ($true) {
    $files = Get-ChildItem -Path $BaseFolder -File
    
    foreach ($file in $files) {
        Write-Host "Uploading: $($file.Name)..."
        
        try {
            $headers = @{
                "x-api-key" = $ApiKey
            }
            
            if ($PSVersionTable.PSVersion.Major -ge 6) {
                $form = @{
                    source_device = $SourceDevice
                    category      = "00_INGEST/Uncategorized"
                    file          = Get-Item -Path $file.FullName
                }
                $response = Invoke-RestMethod -Uri $EndpointUri -Method Post -Headers $headers -Form $form
                Write-Host "Response received. Success."
            } else {
                # Fallback to curl.exe for Windows PowerShell 5.1 compatibility
                Write-Host "PS 5.1 detected. Using curl.exe for multipart upload."
                $curlArgs = @(
                    "-X", "POST",
                    "-H", "x-api-key: $ApiKey",
                    "-F", "source_device=$SourceDevice",
                    "-F", "category=00_INGEST/Uncategorized",
                    "-F", "file=@$($file.FullName)",
                    "-s", "-w", "\n%{http_code}",
                    $EndpointUri
                )
                $output = curl.exe @curlArgs
                $outStr = $output -join ""
                Write-Host "Curl Output: $outStr"
                if ($outStr -notmatch "200$") {
                    throw "Upload failed with status: $outStr"
                }
            }

            # Cleanup
            $destPath = Join-Path $SentFolder $file.Name
            Move-Item -Path $file.FullName -Destination $destPath -Force
            Write-Host "Successfully moved to Sent archive."
            
        } catch {
            Write-Error "Failed to process $($file.Name): $_"
        }
    }
    Start-Sleep -Seconds 2
}
