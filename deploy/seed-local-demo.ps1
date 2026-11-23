# Explicit local demonstration data, never real inventory or product claims.
param([switch]$SyncSearch)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$info=docker inspect simlect-mysql | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $info.Config.Labels.'com.docker.compose.project' -ne 'simlect-local') { throw 'Expected isolated local database.' }
$folder=Join-Path $root 'data/simlect/upload/file/demo'
New-Item -ItemType Directory -Force $folder | Out-Null
Add-Type -AssemblyName System.Drawing
$items=@(@('无线耳机',199,'#dae6ed'),@('机械键盘',299,'#e7dfd6'),@('保温杯',89,'#d9e5db'),@('帆布包',69,'#e9deda'),@('桌面台灯',129,'#e9e4ce'),@('笔记本套装',39,'#dedbed'),@('运动水壶',59,'#d4e6e8'),@('桌面收纳盒',49,'#eadde3'))
$sql=New-Object Collections.Generic.List[string]
$sql.Add('SET NAMES utf8mb4; START TRANSACTION;')
$sql.Add("INSERT IGNORE INTO simlect_product.sys_category VALUES ('D100','本地演示','0',1),('D101','数码演示','D100',1),('D102','生活演示','D100',2);")
for ($i=0;$i -lt $items.Count;$i++) {
  $id='DEMO'+($i+1).ToString('000'); $value=$id+'V'; $name='[本地演示] '+$items[$i][0]; $price=$items[$i][1]; $category=if ($i -lt 2) {'D101'} else {'D102'}; $commend=if ($i -lt 4) {1} else {0}
  $bitmap=New-Object Drawing.Bitmap 800,600
  $g=[Drawing.Graphics]::FromImage($bitmap)
  try {
    $g.Clear([Drawing.ColorTranslator]::FromHtml($items[$i][2]))
    $font=New-Object Drawing.Font 'Microsoft YaHei',32
    $small=New-Object Drawing.Font 'Microsoft YaHei',18
    try { $g.DrawString($items[$i][0],$font,[Drawing.Brushes]::Black,100,230); $g.DrawString('本地演示 · 非真实商品',$small,[Drawing.Brushes]::DimGray,100,320); $bitmap.Save((Join-Path $folder "$id.png"),[Drawing.Imaging.ImageFormat]::Png) } finally { $font.Dispose(); $small.Dispose() }
  } finally { $g.Dispose(); $bitmap.Dispose() }
  $sql.Add("INSERT IGNORE INTO simlect_product.product_info(product_id,product_name,product_desc,cover,create_time,category_id,p_category_id,status,min_price,max_price,total_sale,commend_type) VALUES ('$id','$name','<p>仅供本地功能体验的演示商品，不代表真实商品或实际库存，请勿真实支付。</p>','demo/$id.png',NOW(),'$category','D100',1,$price,$price,0,$commend);")
  $sql.Add("INSERT IGNORE INTO simlect_product.product_property_value(product_id,property_id,property_name,property_sort,cover_type,property_value_id,property_value,sort) VALUES ('$id','DEMO_SPEC','规格',1,0,'$value','演示标准款',1);")
  $sql.Add("INSERT IGNORE INTO simlect_product.product_sku VALUES ('$id',MD5('$value'),'$value',$price,1);")
  $sql.Add("INSERT IGNORE INTO simlect_stock.sku_stock VALUES ('$id',MD5('$value'),100);")
}
$sql.Add('COMMIT;')
$OutputEncoding=New-Object Text.UTF8Encoding($false)
($sql -join "`n") | docker exec -i simlect-mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot --default-character-set=utf8mb4'
if ($LASTEXITCODE -ne 0) { throw 'Demo import failed.' }
Write-Output 'Eight labeled local demo products, categories, images and SKU stocks prepared.'
if ($SyncSearch) {
  $query="SELECT JSON_OBJECT('productId',product_id,'productName',product_name,'productDesc',product_desc,'cover',cover,'categoryId',category_id,'minPrice',min_price,'maxPrice',max_price,'totalSale',total_sale) FROM simlect_product.product_info WHERE product_id IN ('DEMO001','DEMO002','DEMO003','DEMO004','DEMO005','DEMO006','DEMO007','DEMO008');"
  $docs=$query | docker exec -i simlect-mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot --default-character-set=utf8mb4 -N -B --raw'
  if ($LASTEXITCODE -ne 0) { throw 'Demo query failed.' }
  foreach ($json in $docs) {
    $doc=$json | ConvertFrom-Json
    $null=Invoke-RestMethod ("http://127.0.0.1:9200/simlect-index/_doc/"+$doc.productId+'?refresh=true') -Method Put -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($json)) -TimeoutSec 20
  }
  Write-Output 'Demo keyword search index synchronized.'
}
