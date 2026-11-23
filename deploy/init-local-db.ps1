# Only initializes an empty database in the isolated project volume. Never migrates existing data.
$ErrorActionPreference='Stop'
$Root=Split-Path $PSScriptRoot -Parent
$OutputEncoding=New-Object Text.UTF8Encoding($false)
$info=docker inspect simlect-mysql | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Project MySQL container missing.' }
if ($info.Config.Labels.'com.docker.compose.project' -ne 'simlect-local') { throw 'Unexpected Compose project; refusing initialization.' }
if ($info.State.Health.Status -ne 'healthy') { throw 'MySQL not healthy.' }
if (-not ($info.Mounts | Where-Object { $_.Name -eq 'simlect-local_simlect_mysql' -and $_.Destination -eq '/var/lib/mysql' })) { throw 'Unexpected data volume.' }
$client='MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot --default-character-set=utf8mb4 -N -B'
$query="SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name NOT IN ('mysql','sys','performance_schema','information_schema');"
$count=$query | docker exec -i simlect-mysql sh -c $client
if ($LASTEXITCODE -ne 0 -or "$count".Trim() -ne '0') { throw 'Database is not verified empty. No SQL applied; inspect existing schemas manually.' }
$files=@('00_create_databases.sql','00b_nacos_seata_databases.sql','14_nacos.sql','15_seata.sql','16_seata_undo_log.sql','01_user.sql','02_product.sql','03_stock.sql','04_cart.sql','05_order.sql','06_pay.sql','07_coupon.sql','08_search.sql','09_agent.sql','10_admin.sql','13_mq_infra_per_service.sql')
foreach ($name in $files) {
  Write-Host "Applying $name"
  Get-Content (Join-Path $Root "sql/$name") -Raw -Encoding UTF8 | docker exec -i simlect-mysql sh -c $client
  if ($LASTEXITCODE -ne 0) { throw "SQL failed: $name. Partial initialization retained; do not rerun blindly." }
}
"SELECT table_schema,COUNT(*) FROM information_schema.tables WHERE table_schema LIKE 'simlect_%' OR table_schema IN ('nacos','seata') GROUP BY table_schema;" | docker exec -i simlect-mysql sh -c $client
if ($LASTEXITCODE -ne 0) { throw 'Schema verification failed.' }
