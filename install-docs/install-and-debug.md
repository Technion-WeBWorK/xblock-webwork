# 1. Preliminaries
This Tutorial should help the reader to install Webwork xblock and debug it with VS-Code.  

It assumes that the reader have basic experience working with
linux shell commands, python, VS-Code, edx xblocks and docker containers.  

By the end of it You might be able to run a webwork-xblock (django server of it)and debug it through VS-Code (set breakpoints, watch variable values etc')  

Happy ending requires careful follow of the listed steps. Good luck!

# 2. Prerequisites
1. Ubuntu + Python + virtualenv
2. Vscode with python + django + docker extension packs
3. An activated Full webwork docker container that could be started with the subshell command (replace WW/webwork2 with the correct Webwork path):
    >(cd ~/WW/webwork2/ && docker-compose up -d)
4. Detect for correct running with the command
    >firefox --new-window http://localhost:8080/webwork2/admin/

# 3. intalling Ofek webwork xblock
These instructions are based on the Edx instructions here:   
[3.2 Set Up the XBlock Software Development Kit](https://edx.readthedocs.io/projects/xblock-tutorial/en/latest/getting_started/setup_sdk.html)  
and the following chapter  
[3.3. Create Your First XBlock](https://edx.readthedocs.io/projects/xblock-tutorial/en/latest/getting_started/setup_sdk.html)   
>Warning: This version does not include debuging webwork-xblock docker container! only Django server debuging.   
Anyway, a dockering starting point of webwork-xblock could be Tani's 20/1/21 email "xblock-sdk in Docker - using my patched version" 

For practicle reasons I set the xblock directory path **<span style="color:grey">XblockEx</span>**.  
Change it to your needs when following the instructions  

1. Activate full webwork container
   >(cd ~/WW/webwork2/ && docker-compose up -d)  
   *  **<span style="color:grey">/WW/webwork2/</span>** is just my Webwork directory and you should use your own path to this directory

2. create the directory:
    > mkdir XblockEx  
      cd XblockEx  

3. Create and activate python virtual environment:
   >virtualenv venv  
    source venv/bin/activate

4. clone and install edx xblock-sdk:
   >git clone https://github.com/edx/xblock-sdk.git  
    cd xblock-sdk/  
    pip install -r requirements/base.txt  
    cd ..

5. Clone Ofek's webwork xblock:
   >git clone https://github.com/tsabaryg/xblock-webwork.git  
   * You will need to supply a git user and password with access permission.  
   Contact guyts@technion.ac.il or tani@mathnet.technion.ac.il for permission request.

6. Install Ofek's webwork xblock:
   > pip install -e xblock-webwork

7. Create the SQLite Database([3.3.3](https://edx.readthedocs.io/projects/xblock-tutorial/en/latest/getting_started/create_first_xblock.html#create-the-sqlite-database:)).  
Notice that the first 2 commands and the last one are not Originally listed but mandatory for proper installation
   >mkdir var  
   pip install mock  
   python xblock-sdk/manage.py migrate  
   pip install xblock_utils

8. Run the webwork-xblock Django server:  
   > python xblock-sdk/manage.py runserver  
   
9.  Check it out to work properly in your bowser:  
    >http://localhost:8000
    
    >![Alt](Webwork-Xblock-Browser-Entry-Page.png)  
10. Clicking one of the problems (here I took the first one), may typically look like this:  
    >![Alt](Webwork-Xblock-Browser-Typical-Problem-Page.png)

# 4.  Debug the webwork-xblock (Django server) with VS-Code
1. Open your VS-Code
2. Open the XblockEx Folder:
   >File -> Open Folder -> open XblockEx -> xblock-sdk
3. Choose the correct venv python inerpreter:
   >View -> Command Palette -> Python: Select Interpreter -> Enter interpreter path -> Find..->  
   scroll to ~/XblockEx-> venv -> bin and choose python3.8
4. Open new terminal with activated venv:
   >Terminal->New terminal choose new terminal and it will open this terminal with the virtual environment activated:
   ![Alt](VS-Code-Terminal-with-venv-activated.png)  
5. Create a basic launch.json file adapted to running Django
   server of the type Python -> Django
   ![Alt](VS-Code-Create-launch.json.png)
6. This will end with .vscode directory with the basic Python/Django launch.json file inside:  
   >![Alt](VS-Code-Python-Django-launch.json.png)
7. Place breakpoints in some interesting points (./manage.py, ./workbench/views.py, XblockEx/xblock-webwork/webwork/webwork.py):
   >![Alt](VS-Code-BreakPoints.png) 
8. In Run sidebar choose the correct debug configuration (Python: Django) and press the green rectangle (F5 will equally work):  
   >![Alt](VS-Code-Debug.png) 
9. Open the browser at http://127.0.0.1:8000/  
   and notice the interaction of the browser actions with your breakpoints
10. You are ready to develop/debug process of this project. Enjoy.