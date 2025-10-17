#Using Py 3.12.0 (download if necessary)

> py -3.12 -m venv .venv
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> .venv\Scripts\Activate.ps1
> python -m pip install -r requirements.txt
> python -m playwright install
> python .\scripts\run_niap.py
