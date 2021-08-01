<!--
Colors convention: a Bootstrap-like color convention is followed see e.g.
https://www.w3schools.com/bootstrap4/bootstrap_colors.asp

Uncomment these HTML lines to see the effect and
copy-paste in document up to need

<span style="color:#0275d8">Primary text</span>  
<span style="color:#5cb85c">Success text</span>  
<span style="color:#5bc0de">Info text here</span>  
<span style="color:#f0ad4e">Warning text</span>  
<span style="color:#d9534f">Danger text</span>  
<span style="color:#f7f7f7">Faded text</span>  
-->

**Warning:** We have not used the XBlock SDK with the WeBWorK XBlock for a
long time. Some features, in particular the course-level settings from
"Other course settings" and settings related to deadlines, graceperiod,
and probably more would not be available in the SDK. As a result, attempting
to run the WeBWorK XBlock in the DSK is not recommended nor supported.

# 1. Preliminaries
This Tutorial should help the reader to install xblock-webwork into Open edX's limited xblock-sdk environment and debug it with VS-Code. Listed below xblock-sdk environment pros-and-cons when compared with Open edX-devstack environment:

**Pros:**
+ Light weight (with disc/cash/cpu usage)
+ Easily installed
+ Easily debugged
+ Fast developing process

**Cons:**
- Does not follow the full/accurate view of Open edX's  
  course site. It rather show's the xblock limited view
- Basically does not support course deadlines, grades, and  
  other LMS management operations
- Therefore with limited development capabilities

It assumes that the reader have basic experience working with  
- linux shell commands
- python
- VS-Code
- Open edX's xblocks
- Docker containers

Following this tutorial up to a successful end, will arm you with the capabilities of running webwork-xblock (django server of it) in xblock-sdk environment and debug it through VS-Code (set breakpoints, watch variable values etc') 

Happy ending requires careful follow of the listed steps.

**Good luck!**

# 2. Prerequisites
1. Ubuntu + Python + virtualenv
2. Vscode with python + django + docker extension packs
3. An activated Full webwork docker container that could be started with the subshell command (replace WW/webwork2 with the correct Webwork path):
    >(cd ~/WW/webwork2/ && docker-compose up -d)
* To make sure that the local webwork server runs correctly, execute the shell command:
    >firefox --new-window http://localhost:8080/webwork2/admin/

# 3. installing the webwork xblock
These instructions are based on the Edx instructions here:   
[3.2 Set Up the XBlock Software Development Kit](https://edx.readthedocs.io/projects/xblock-tutorial/en/latest/getting_started/setup_sdk.html)  
and the following chapter  
[3.3. Create Your First XBlock](https://edx.readthedocs.io/projects/xblock-tutorial/en/latest/getting_started/setup_sdk.html)   

<span style="color: #f0ad4e">**Warning:**  
    This version does not include debugging webwork-xblock docker container!  
    It only local Django server debugging.   
    Anyway, a good starting point to accomplish docker container debugging could be found  
    in the complement instruction set devstack-install-and-debug.md 
</span>  

**<span style="color:#0275d8">XblockEx</span>** directory name was selected for practical explanation reasons.  
Change it to your needs when following the instructions  

1. Activate full webwork container
   >(cd ~/WW/webwork2/ && docker-compose up -d)  
   *  **<span style="color:#0275d8">/WW/webwork2/</span>**   
   is just my Webwork directory and you should use your own path to this directory

2. Create the directory:
    > mkdir XblockEx  
      cd XblockEx  

3. Create and activate python virtual environment:
   >virtualenv venv  
    source venv/bin/activate

4. Clone and install edx xblock-sdk:
   >git clone https://github.com/edx/xblock-sdk.git  
    cd xblock-sdk/  
    pip install -r requirements/base.txt  
    cd ..

5. Clone the webwork xblock:
   > git clone https://github.com/Technion-WeBWorK/xblock-webwork.git

6. Install the webwork xblock:
   > pip install -e xblock-webwork

7. Create the SQLite Database([3.3.3](https://edx.readthedocs.io/projects/xblock-tutorial/en/latest/getting_started/create_first_xblock.html#create-the-sqlite-database:)).  
Notice that the first 2 commands and the last one are not Originally listed but mandatory for proper installation
   >mkdir var  
   pip install mock  
   python xblock-sdk/manage.py migrate  
   pip install xblock_utils

8. Run the webwork-xblock Django server:  
   > python xblock-sdk/manage.py runserver  
   
9.  Check it out to work properly in your browser:  
    http://localhost:8000  
    ![Alt](Webwork-Xblock-Browser-Entry-Page.png)  
10. Clicking one of the problems (here I took the first one), may 
    typically look like this:  
    ![Alt](Webwork-Xblock-Browser-Typical-Problem-Page.png)

# 4.  Debug the webwork-xblock (Django server) with VS-Code
1. Open your VS-Code
2. Open the XblockEx Folder:
   >File -> Open Folder -> open XblockEx -> xblock-sdk
3. Choose the correct venv python interpreter:
   >View -> Command Palette -> Python: Select Interpreter -> Enter interpreter path -> Find..->  
   scroll to ~/XblockEx-> venv -> bin and choose python3.8
4. Open new terminal with activated venv:  
   > Terminal->New terminal choose new terminal and it will open this terminal with the virtual environment activated:  
   
   ![Alt](VS-Code-Terminal-with-venv-activated.png)  
5. Create a basic launch.json file adapted to running Django
   server of the type Python -> Django
   ![Alt](VS-Code-Create-launch.json.png)
6. This will end with .vscode directory with the basic Python/Django launch.json file inside:  
   ![Alt](VS-Code-Python-Django-launch.json.png)
7. Place breakpoints in some interesting points (./manage.py, ./workbench/views.py, XblockEx/xblock-webwork/webwork/webwork.py):
   ![Alt](VS-Code-BreakPoints.png) 
8. In Run sidebar choose the correct debug configuration (Python: Django) and press the green rectangle (F5 will equally work):  
   ![Alt](VS-Code-Debug.png) 
9. Open the browser at http://127.0.0.1:8000/  
   and notice the interaction of the browser actions with your breakpoints
10. You are ready to develop/debug process of this project.

<span style="color:#5cb85c">**Happy debugging**</span>
