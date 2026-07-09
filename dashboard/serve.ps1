# Minimal HTTP server for serving the dashboard locally.
# Usage: powershell -File serve.ps1
# Then open http://localhost:8743 in your browser.

$port    = 8080
$root    = $PSScriptRoot   # same folder as index.html and data.json
$prefix  = "http://localhost:$port/"

# If port is taken, try incrementing until we find a free one
while ($true) {
    $test = New-Object System.Net.HttpListener
    $test.Prefixes.Add($prefix)
    try { $test.Start(); $test.Stop(); break }
    catch { $port++; $prefix = "http://localhost:$port/" }
}

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add($prefix)
$listener.Start()

Write-Host "Serving $root on $prefix  (Ctrl+C to stop)"

$mimeTypes = @{
    ".html" = "text/html; charset=utf-8"
    ".json" = "application/json; charset=utf-8"
    ".js"   = "application/javascript; charset=utf-8"
    ".css"  = "text/css; charset=utf-8"
    ".png"  = "image/png"
    ".ico"  = "image/x-icon"
}

while ($listener.IsListening) {
    $ctx  = $listener.GetContext()
    $req  = $ctx.Request
    $resp = $ctx.Response

    $rawPath = $req.Url.LocalPath
    if ($rawPath -eq "/") { $rawPath = "/index.html" }

    $filePath = Join-Path $root ($rawPath.TrimStart("/").Replace("/", "\"))

    if (Test-Path $filePath -PathType Leaf) {
        $ext         = [System.IO.Path]::GetExtension($filePath).ToLower()
        $mime        = if ($mimeTypes[$ext]) { $mimeTypes[$ext] } else { "application/octet-stream" }
        $bytes       = [System.IO.File]::ReadAllBytes($filePath)
        $resp.ContentType   = $mime
        $resp.ContentLength64 = $bytes.Length
        $resp.OutputStream.Write($bytes, 0, $bytes.Length)
    } else {
        $resp.StatusCode = 404
        $msg  = [System.Text.Encoding]::UTF8.GetBytes("404 Not Found: $rawPath")
        $resp.OutputStream.Write($msg, 0, $msg.Length)
    }

    $resp.OutputStream.Close()
}
