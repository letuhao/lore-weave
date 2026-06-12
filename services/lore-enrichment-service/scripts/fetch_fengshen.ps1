# One-off fetcher (NOT committed): pull verbatim PD 封神演義 chapters from
# zh.wikisource via direct raw HTTP (no LLM), strip wiki markup → plain prose,
# write fixtures under scripts/seed_data/fengshen/. Polite UA + delay.
param([int]$From = 1, [int]$To = 20)

$ua = "LoreWeave-dev/1.0 (enrichment PD corpus seeding; contact letuhao1994@gmail.com)"
$outdir = "services/lore-enrichment-service/scripts/seed_data/fengshen"
New-Item -ItemType Directory -Force -Path $outdir | Out-Null

for ($i = $From; $i -le $To; $i++) {
    $n = "{0:D3}" -f $i
    $url = "https://zh.wikisource.org/wiki/%E5%B0%81%E7%A5%9E%E6%BC%94%E7%BE%A9/%E5%8D%B7${n}?action=raw"
    try {
        $raw = (Invoke-WebRequest -Uri $url -Headers @{ "User-Agent" = $ua } -UseBasicParsing -TimeoutSec 30).Content
    } catch {
        Write-Output "卷$n FAIL: $($_.Exception.Message)"; Start-Sleep -Milliseconds 800; continue
    }
    # section title (for the header line) from the Header template
    $title = ""
    if ($raw -match '(?m)^\s*\|\s*section\s*=\s*(.+?)\s*$') { $title = $Matches[1].Trim() }
    # strip the leading {{Header ...}} template, then any remaining templates + wiki links + categories
    $body = $raw -replace '(?s)^\s*\{\{\s*Header.*?\}\}\s*', ''
    $body = $body -replace '(?s)\{\{[^{}]*\}\}', ''
    $body = $body -replace '\[\[[^\]|]*\|([^\]]*)\]\]', '$1'
    $body = $body -replace '\[\[([^\]]*)\]\]', '$1'
    $body = $body -replace '(?m)^.*[Cc]ategory:.*$', ''
    $body = $body -replace '(?m)^\s*分類[:：].*$', ''
    $body = $body.Trim()
    if ($body.Length -lt 800) { Write-Output "卷$n SHORT ($($body.Length)) — skipped"; Start-Sleep -Milliseconds 800; continue }
    $header = if ($title) { "封神演義 $title`n`n" } else { "封神演義 第$($i)回`n`n" }
    $path = Join-Path $outdir ("卷$n.txt")
    Set-Content -Path $path -Value ($header + $body) -Encoding UTF8 -NoNewline
    Write-Output "卷$n OK ($($body.Length) chars) -> $title"
    Start-Sleep -Milliseconds 800
}
