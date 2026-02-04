# PowerShell 7+ | запуск: pwsh -ExecutionPolicy Bypass -File .\repair_project.ps1
$ErrorActionPreference = "Stop"
$SRC = Join-Path $PWD "src"
if (!(Test-Path $SRC)) { throw "src not found: $SRC" }

# 0) Backup
$stamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
$backup = "backup_src_$stamp.zip"
if (Test-Path $backup) { Remove-Item $backup -Force }
Compress-Archive -Path (Join-Path $SRC "*") -DestinationPath $backup
Write-Host "Backup: $backup"

# Stats
$stats = [ordered]@{
  Files = 0
  DoubleQuotesFixed = 0
  SmartQuotesFixed = 0
  ClassAttrFixed = 0
  OptionValueFixed = 0
  ArrowFixed = 0
  SelfCloseFixed = 0
}

function Count-Matches([string]$text, [string]$pattern) {
  return ([regex]::Matches($text, $pattern)).Count
}

function Fix-Content([string]$text) {
  # 1) "" -> "
  $stats.DoubleQuotesFixed += Count-Matches $text '""'
  $text = $text -replace '""','"'

  # 2) “ ” « » ‘ ’ -> нормальные
  $stats.SmartQuotesFixed += Count-Matches $text '[“”«»‘’]'
  $text = $text -replace '[“”«»]', '"'
  $text = $text -replace '[‘’]', "'"

  # 3) class= -> className=
  $stats.ClassAttrFixed += Count-Matches $text '(\s)class='
  $text = $text -replace '(\s)class=', '$1className='

  # 4) <option value=">Текст</option> -> <option value="">Текст</option>
  $stats.OptionValueFixed += Count-Matches $text '<option\s+value=">([^<]*)</option>'
  $text = [regex]::Replace($text, '<option\s+value=">([^<]*)</option>', '<option value="">$1</option>')

  # 5) onChange={(e) = /> ...} -> onChange={(e) => ...}
  $stats.ArrowFixed += Count-Matches $text '\)\s*=\s*/>\s*'
  $text = $text -replace 'onChange=\{\s*\(e\)\s*=\s*/>\s*', 'onChange={(e) => '

  # 6) Самозакрыть одиночные теги
  $stats.SelfCloseFixed += Count-Matches $text '<(input|img|br|hr)([^>/]*?)>(?!\s*/>)'
  $text = [regex]::Replace($text, '<(input|img|br|hr)([^>/]*?)>(?!\s*/>)', '<$1$2 />')

  return $text
}

# 1) Пройти по всем исходникам
$extensions = @('*.jsx','*.tsx','*.js','*.ts')
Get-ChildItem -Recurse -Path $SRC -Include $extensions | ForEach-Object {
  $path = $_.FullName
  $txt = Get-Content $path -Raw
  $fixed = Fix-Content $txt
  if ($fixed -ne $txt) {
    Set-Content -Path $path -Value $fixed -Encoding utf8
  }
  $stats.Files++
}

# 2) Перезаписать ThemeSwitch.jsx (гарантированно валидный)
$themeSwitchPath = Join-Path $SRC "components/ThemeSwitch.jsx"
$themeSwitchContent = @'
export default function ThemeSwitch({ theme, onChange }) {
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      className="btn"
      title={`Switch to ${next}`}
      onClick={() => onChange(next)}
      style={{ background: "var(--surface)", color: "var(--txt)", border: "var(--border)" }}
    >
      {theme === "dark" ? "Dark" : "Light"}
    </button>
  );
}
'@
if (!(Test-Path (Split-Path $themeSwitchPath -Parent))) {
  New-Item -ItemType Directory -Force -Path (Split-Path $themeSwitchPath -Parent) | Out-Null
}
Set-Content -Path $themeSwitchPath -Value $themeSwitchContent -Encoding utf8

# 3) Точечные фиксы Assets.jsx
$assetsPath = Join-Path $SRC "pages/Assets.jsx"
if (Test-Path $assetsPath) {
  $a = Get-Content $assetsPath -Raw
  $a = $a -replace 'onChange=\{\s*\(e\)\s*=\s*/>\s*', 'onChange={(e) => '
  $a = $a -replace '<option value=">Сотрудник</option>','<option value="">Сотрудник</option>'
  $a = $a -replace '<option value=">Предмет</option>','<option value="">Предмет</option>'
  $a = $a -replace 'value=\{filters\.dateFrom\}', 'value={filters?.dateFrom ?? ""}'
  $a = $a -replace 'value=\{filters\.dateTo\}',   'value={filters?.dateTo ?? ""}'
  Set-Content -Path $assetsPath -Value $a -Encoding utf8
}

# 4) Итог
Write-Host "=== FIX REPORT ==="
$stats.GetEnumerator() | ForEach-Object { "{0,-20} {1}" -f $_.Key, $_.Value } | Write-Host
Write-Host "Run: npm run dev"
