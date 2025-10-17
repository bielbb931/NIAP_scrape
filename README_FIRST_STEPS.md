#Using Py 3.12.0 
...older version is more supported (lag for pandas support) and ChatGPT has a better understanding of older versions (pre-training lag)

#Bypass Execution Policies
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
...temporary workaround since PowerShell blocks scripts from being run for some reason?

#Activate your virtual environment
> py -m venv v.env
...creates environment (if not already created)

#Install the tools
> python -m pip install -r requirements.txt
...runs pip with your Python to install every package listed in requirements.txt into your current environment
> python -m playwright install chromium
...tells Playwright to download and set up the Chromium browser that the scraper will automate

#Run script
> 