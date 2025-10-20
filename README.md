#Using Py 3.12.0 (download if necessary)
...download zip file, extract, then open windows powershell terminal in extracted folder

> py -3.12 -m venv .venv

> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

> .venv\Scripts\Activate.ps1

> python -m pip install -r requirements.txt

> python -m playwright install

> python .\scripts\run_niap.py
