# Register Telegram's webhook without printing the bot token.
$ErrorActionPreference = "Stop"

$workerUrl = "https://bot-control-ac.99lq9ohj-kfshcd.workers.dev/telegram"

$tokenSecure = Read-Host "Paste BOT_TOKEN from BotFather" -AsSecureString
$secretSecure = Read-Host "Paste TELEGRAM_WEBHOOK_SECRET configured in Cloudflare" -AsSecureString
$token = [System.Net.NetworkCredential]::new("", $tokenSecure).Password
$secret = [System.Net.NetworkCredential]::new("", $secretSecure).Password

if ([string]::IsNullOrWhiteSpace($token) -or $token -notmatch '^\d+:[A-Za-z0-9_-]+$') {
  throw "BOT_TOKEN format is invalid."
}
if ([string]::IsNullOrWhiteSpace($secret) -or $secret.Length -gt 256 -or $secret -notmatch '^[A-Za-z0-9_-]+$') {
  throw "TELEGRAM_WEBHOOK_SECRET must contain 1-256 characters: letters, digits, underscore or hyphen."
}

$body = @{
  url = $workerUrl
  secret_token = $secret
  allowed_updates = @("message", "edited_message")
  max_connections = 20
  drop_pending_updates = $false
} | ConvertTo-Json -Depth 5

try {
  $result = Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$token/setWebhook" -ContentType "application/json" -Body $body
  if ($result.ok -and $result.result) {
    Write-Host "Webhook registered successfully." -ForegroundColor Green
    $info = Invoke-RestMethod -Method Get -Uri "https://api.telegram.org/bot$token/getWebhookInfo"
    Write-Host ("Webhook URL: " + $info.result.url)
    Write-Host ("Pending updates: " + $info.result.pending_update_count)
  } else {
    throw "Telegram did not confirm the webhook."
  }
}
finally {
  $token = $null
  $secret = $null
  $tokenSecure = $null
  $secretSecure = $null
  $body = $null
}
