param(
    [ValidateSet("film", "draft", "radio-cut", "rough-cut", "validate", "smoke", "test")]
    [string]$Target = "film",
    [ValidateSet("auto", "live", "mock")]
    [string]$Mode = "auto"
)

$ErrorActionPreference = "Stop"
$Python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }

switch ($Target) {
    "film"      { & $Python -m pipeline run --quality final --mode $Mode }
    "draft"     { & $Python -m pipeline run --quality draft --mode $Mode }
    "radio-cut" { & $Python -m pipeline validate; & $Python -m pipeline narration --mode $Mode; & $Python -m pipeline assemble --radio-cut }
    "rough-cut" { & $Python -m pipeline validate; & $Python -m pipeline narration --mode $Mode; & $Python -m pipeline keyframes --mode $Mode; & $Python -m pipeline music --mode $Mode; & $Python -m pipeline assemble --rough-cut }
    "validate"  { & $Python -m pipeline validate }
    "smoke"     { & $Python -m pipeline smoke --mode $Mode }
    "test"      { & $Python -m pytest -v }
}
