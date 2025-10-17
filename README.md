#Using Py 3.12.0

#Bypass Execution Policies
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
...temporary workaround if needed

#Activate your virtual environment
> py -m venv v.env

#Install the tools
> python -m pip install -r requirements.txt
> python -m playwright install chromium

#Run script
> python scripts\ run_niap
