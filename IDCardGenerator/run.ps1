# Launch ID Card Generator using the project venv.
# Sets TCL_LIBRARY and TK_LIBRARY so tkinter can find Tcl8.6/Tk8.6
# even when running from a virtualenv on Windows.

$pyHome = "C:\Users\HARI\AppData\Local\Programs\Python\Python313"

$env:TCL_LIBRARY = "$pyHome\tcl\tcl8.6"
$env:TK_LIBRARY  = "$pyHome\tcl\tk8.6"

$venvPy = Join-Path $PSScriptRoot "venv\Scripts\python.exe"

& $venvPy (Join-Path $PSScriptRoot "app.py")
