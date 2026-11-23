# Creates one demo order and simulates payment. Uses only the isolated local environment.
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$settings=@{}
Get-Content "$root/Simlect-backend/Simlect-agent/.env" | ForEach-Object {
  if ($_ -match '^([A-Z][A-Z0-9_]*)=(.*)$') { $settings[$matches[1]]=$matches[2] }
}
if ($settings.SIMLECT_PAY_LOCAL_MOCK_ENABLED -ne 'true') { throw 'Local payment mode required.' }
$session=New-Object Microsoft.PowerShell.Commands.WebRequestSession
$base='http://127.0.0.1:6001'
$headers=@{'X-Requested-With'='XMLHttpRequest';Origin=$base}
function Api($path,$body=$null,$json=$false) {
  $args=@{Uri=($base+$path);WebSession=$session;Headers=$headers;TimeoutSec=25}
  if ($null -ne $body) { $args.Method='Post'; $args.Body=$body }
  if ($json) { $args.ContentType='application/json'; $args.Body=($body | ConvertTo-Json -Depth 8 -Compress) }
  $response=Invoke-RestMethod @args
  if ($response.code -ne 200) { throw "$path returned $($response.code): $($response.info)" }
  Write-Host "PASS $path"
  return $response.data
}
function CaptchaCode($captcha) {
  $value=docker exec simlect-redis redis-cli --raw GET ('mall:checkcode:'+$captcha.checkCodeKey)
  if ($LASTEXITCODE -ne 0 -or -not $value) { throw 'Local CAPTCHA lookup failed.' }
  return $value.Trim('"')
}
$captcha=Api '/api/account/checkCode'
$null=Api '/api/account/login' @{email=$settings.LOCAL_DEMO_EMAIL;password=$settings.LOCAL_DEMO_PASSWORD;checkCodeKey=$captcha.checkCodeKey;checkCode=(CaptchaCode $captcha)}
$null=Api '/api/account/getUserInfo'
$null=Api '/api/product/loadCategory'
$null=Api '/api/product/getProduct' @{productId='DEMO001'}
$search=Api '/api/search/products' @{keyWords='DEMO';pageNo=1}
# Search uses Chinese product names, so also assert a known Chinese term via Unicode literals.
$term=[string][char]0x8033+[char]0x673A
$search=Api '/api/search/products' @{keyWords=$term;pageNo=1}
if ($search.totalCount -lt 1) { throw 'Known demo product not indexed.' }
$null=Api '/api/productCart/add2Cart' @{productId='DEMO001';propertyValueIds='DEMO001V';buyCount=1}
$cart=Api '/api/productCart/loadProductCart' @{pageNo=1}
if ($cart.totalCount -lt 1) { throw 'Cart unexpectedly empty.' }
$addresses=Api '/api/userAddress/loadDataList'
$address=$addresses | Where-Object { $_.addressee -eq 'Local demo' } | Select-Object -First 1
if (-not $address) {
  $null=Api '/api/userAddress/addAddress' @{address='LOCAL DEMO - no physical delivery';addressee='Local demo';phone='13800000000';defaultType=1}
  $address=(Api '/api/userAddress/loadDataList' | Where-Object { $_.addressee -eq 'Local demo' } | Select-Object -First 1)
}
$mode=Api '/api/order/paymentMode'
if (-not $mode.localMock) { throw 'Server did not enable local payment mode.' }
$pay=Api '/api/order/postOrder' @{payMethod='alipay_pc';addressId=$address.addressId;orderFrom=0;orderList=@(@{productId='DEMO001';propertyValueIds='DEMO001V';buyCount=1;remark='Local demo simulation'})} $true
if (-not $pay.payOrderId) { throw 'Missing payment order ID.' }
$lookupId=if ($pay.orderId) { $pay.orderId } else { $pay.payOrderId }
$null=Api '/api/order/localPay' @{orderId=$lookupId}
$order=Api '/api/order/getOrderInfo' @{payOrderId=$pay.payOrderId}
if ($order.orderStatus -ne 1) { throw 'Order did not reach paid state.' }
$null=Api '/api/order/loadMyOrder' @{pageNo=1}
$null=Api '/api/account/logout' @{}
Write-Host 'PASS local demo checkout and simulated payment (no real charge).'
