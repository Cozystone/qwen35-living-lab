# 빌드 PC 방화벽: 실험 노트북용 포트 열기/닫기 (관리자 권한 필요). 사용자 승인 2026-10-26.
#   열기:  powershell -ExecutionPolicy Bypass -File firewall_lab.ps1 open
#   8000 닫기(설치 끝난 뒤): ... firewall_lab.ps1 close-install
#   원상복구(전부): ... firewall_lab.ps1 restore
param([ValidateSet('open', 'close-install', 'restore')] [string]$Mode = 'open')
$log = 'D:\Qwen3.5-4B-Heretic\logs\firewall_lab.log'
$name = 'Qwen35-lab-LAN'
$block = Get-NetFirewallApplicationFilter | Where-Object { $_.Program -like '*Qwen3.5-4B-Heretic*python*' } |
    Get-NetFirewallRule | Where-Object { $_.Action -eq 'Block' }
& {
    "== $(Get-Date -Format s) mode=$Mode"
    switch ($Mode) {
        'open' {
            $block | Disable-NetFirewallRule
            Remove-NetFirewallRule -Name $name -ErrorAction SilentlyContinue
            New-NetFirewallRule -Name $name -DisplayName 'Qwen35-lab: install(8000)+gateway(8899) LAN only' -Direction Inbound `
                -Action Allow -Protocol TCP -LocalPort 8000, 8899 -RemoteAddress 192.168.0.0/24 -Profile Private | Out-Null
        }
        'close-install' { Set-NetFirewallRule -Name $name -LocalPort 8899 }
        'restore' { Remove-NetFirewallRule -Name $name -ErrorAction SilentlyContinue; $block | Enable-NetFirewallRule }
    }
    $block | Get-NetFirewallRule | ForEach-Object { "block rule {0} enabled={1}" -f $_.Name, $_.Enabled }
    Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue | ForEach-Object {
        $p = $_ | Get-NetFirewallPortFilter; $a = $_ | Get-NetFirewallAddressFilter
        "allow rule {0} enabled={1} ports={2} remote={3} profile={4}" -f $_.Name, $_.Enabled, ($p.LocalPort -join ','), ($a.RemoteAddress -join ','), $_.Profile
    }
} *>&1 | Out-File -Append -Encoding utf8 $log
