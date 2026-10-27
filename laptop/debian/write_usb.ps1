# Debian ISO 를 USB 에 원시(DD) 기록하고 다시 읽어 SHA-256 을 확인한다. 관리자 권한 필요.
# 사용자 승인(2026-10-26): 디스크 2 = VendorCo ProductCode 7.5GB USB(ESD-USB) 를 지우고 기록.
# 안전장치: BusType=USB, 크기 7~8GB, 시리얼 일치가 모두 맞아야만 진행. 하나라도 다르면 아무것도 안 하고 종료.
param(
    [string]$Serial = '2791651296744543834',
    [string]$Iso = 'D:\Qwen3.5-4B-Heretic\laptop\debian\debian-13.7.0-amd64-netinst.iso',
    [string]$Expected = 'a7ef94ac2fb9a7fec454552abd629b7cc9d5155c886165a45649f5ce6167e355',
    [string]$Log = 'D:\Qwen3.5-4B-Heretic\logs\write_usb.log'
)
$ErrorActionPreference = 'Stop'
function L($m) { "$(Get-Date -Format s) $m" | Tee-Object -FilePath $Log -Append }

try {
    $d = @(Get-Disk | Where-Object { $_.SerialNumber -eq $Serial })
    if ($d.Count -ne 1) { throw "serial $Serial 디스크가 정확히 1개가 아님 ($($d.Count))" }
    $d = $d[0]
    if ($d.BusType -ne 'USB') { throw "BusType=$($d.BusType) (USB 아님)" }
    if ($d.Size -lt 7GB -or $d.Size -gt 8GB) { throw "크기 $($d.Size) 가 7~8GB 범위 밖" }
    if ($d.IsBoot -or $d.IsSystem) { throw "부팅/시스템 디스크" }
    L "target: disk $($d.Number) $($d.FriendlyName) $([math]::Round($d.Size/1GB,1))GB serial=$Serial"

    $isoLen = (Get-Item $Iso).Length
    if ($isoLen % 512) { throw "ISO 크기가 512 배수가 아님" }
    if ((Get-FileHash $Iso -Algorithm SHA256).Hash.ToLower() -ne $Expected) { throw "ISO 해시 불일치" }

    # 이동식 디스크는 offline 전환이 안 됨(Not Supported). 파티션을 지우면 마운트된 볼륨이 없어 바로 기록 가능.
    if ($d.PartitionStyle -ne 'RAW') {
        L "clear-disk (파티션 제거)"
        Clear-Disk -Number $d.Number -RemoveData -RemoveOEM -Confirm:$false
    }

    $dev = "\\.\PhysicalDrive$($d.Number)"
    L "write $isoLen bytes -> $dev"
    $buf = New-Object byte[] (4MB)
    $src = [IO.File]::OpenRead($Iso)
    $dst = New-Object IO.FileStream($dev, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite, 4MB, [IO.FileOptions]::WriteThrough)
    while (($n = $src.Read($buf, 0, $buf.Length)) -gt 0) {
        if ($n % 512) { [Array]::Clear($buf, $n, 512 - $n % 512); $n += 512 - $n % 512 }
        $dst.Write($buf, 0, $n)
    }
    $dst.Flush(); $dst.Close(); $src.Close()

    L "read back + sha256"
    $sha = [Security.Cryptography.SHA256]::Create()
    $rd = New-Object IO.FileStream($dev, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite, 4MB)
    $left = $isoLen
    while ($left -gt 0) {
        $want = [int][Math]::Min($buf.Length, $left)
        $n = $rd.Read($buf, 0, $want)
        if ($n -le 0) { throw "read back 중단" }
        [void]$sha.TransformBlock($buf, 0, $n, $null, 0); $left -= $n
    }
    [void]$sha.TransformFinalBlock($buf, 0, 0); $rd.Close()
    $got = -join ($sha.Hash | ForEach-Object { $_.ToString('x2') })
    if ($got -ne $Expected) { throw "검증 실패: $got" }
    L "OK: USB 내용 SHA-256 = $got (ISO 와 일치)"
} catch {
    L "FAILED: $($_.Exception.Message)"
    exit 1
}
