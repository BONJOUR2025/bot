# PowerShell 7+ | запуск: pwsh -ExecutionPolicy Bypass -File .\repair_all.ps1
$ErrorActionPreference = "Stop"
$SRC = Join-Path $PWD "src"
if (!(Test-Path $SRC)) { throw "src not found: $SRC" }

# 0) Backup
$stamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
$backup = "backup_src_$stamp.zip"
if (Test-Path $backup) { Remove-Item $backup -Force }
Compress-Archive -Path (Join-Path $SRC "*") -DestinationPath $backup
Write-Host "Backup: $backup"

# stats
$stats = [ordered]@{ Files=0; DoubleQuotes=0; SmartQuotes=0; ClassAttr=0; OptionFix=0; SelfClose=0; ArrowGeneric=0; ArrowHandlers=0 }

function Count($t,$p){ ([regex]::Matches($t,$p)).Count }

function Fix-Text([string]$t){
  # "" -> "
  $stats.DoubleQuotes += Count $t '""'
  $t = $t -replace '""','"'

  # “ ” « » ‘ ’ -> обычные
  $stats.SmartQuotes += Count $t '[“”«»‘’]'
  $t = $t -replace '[“”«»]', '"' -replace '[‘’]', "'"

  # class= -> className=
  $stats.ClassAttr += Count $t '(\s)class='
  $t = $t -replace '(\s)class=', '$1className='

  # <option value=">Текст</option> -> <option value="">Текст</option>
  $stats.OptionFix += Count $t '<option\s+value=">([^<]*)</option>'
  $t = [regex]::Replace($t, '<option\s+value=">([^<]*)</option>', '<option value="">$1</option>')

  # Самозакрывающиеся одиночные теги
  $stats.SelfClose += Count $t '<(input|img|br|hr)([^>/]*?)>(?!\s*/>)'
  $t = [regex]::Replace($t, '<(input|img|br|hr)([^>/]*?)>(?!\s*/>)', '<$1$2 />')

  # Грубая починка ) = />  -> ) =>   (на случай странной вёрстки)
  $stats.ArrowGeneric += Count $t '\)\s*=\s*/>\s*'
  $t = $t -replace '\)\s*=\s*/>\s*', ') => '

  # Точная починка обработчиков: onXxx={ (params) = />  ... } -> onXxx={(params) =>  ...}
  $regex = New-Object Regex 'on(?<ev>[A-Za-z0-9_]+)\s*=\s*\{\s*\((?<params>[^\)]*)\)\s*=\s*/>\s*', 'Singleline'
  $countBefore = ($regex.Matches($t)).Count
  if ($countBefore -gt 0) {
    $t = $regex.Replace($t, {
      param($m)
      'on' + $m.Groups['ev'].Value + '={(' + $m.Groups['params'].Value + ') => '
    })
    $stats.ArrowHandlers += $countBefore
  }

  return $t
}

$exts = @('*.jsx','*.tsx','*.js','*.ts')
Get-ChildItem -Recurse -Path $SRC -Include $exts | ForEach-Object {
  $p = $_.FullName
  $txt = Get-Content $p -Raw
  $fixed = Fix-Text $txt
  if ($fixed -ne $txt) {
    Set-Content -Path $p -Value $fixed -Encoding utf8
  }
  $stats.Files++
}

# Перезаписать ThemeSwitch.jsx (валидный)
$tsPath = Join-Path $SRC "components/ThemeSwitch.jsx"
$tsCode = @'
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
if (!(Test-Path (Split-Path $tsPath -Parent))) { New-Item -ItemType Directory -Force -Path (Split-Path $tsPath -Parent) | Out-Null }
Set-Content -Path $tsPath -Value $tsCode -Encoding utf8

# Итог
Write-Host "=== FIX REPORT ==="
$stats.GetEnumerator() | ForEach-Object { "{0,-16} {1}" -f $_.Key, $_.Value } | Write-Host
Write-Host "Now: npm run dev"
