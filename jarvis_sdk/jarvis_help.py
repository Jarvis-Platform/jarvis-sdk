# -*- coding: utf-8 -*-

def display_help():

    help = """
Jarvis SDK Help
===============
usage : jarvis COMMAND ARGUMENTS


Configure Jarvis SDK
--------------------
usage : jarvis config


Authenticate with Firebase
--------------------------
usage : jarvis auth login


Configuration checking
-----------------------
Please type : jarvis check configuration help


Configuration creation
-----------------------
Please type : jarvis create configuration help


Configuration deployment
------------------------
Please type : jarvis deploy configuration help


Google Cloud Platform Cloud Functions deployment
------------------------------------------------
Please type : jarvis deploy gcp-cloud-function help


Encrypt Message of file content
-------------------------------
Will encrypt data using Jarvis Public Key.

To encrypt a simple message : jarvis encrypt "My message to encrypt."
To encrypt file content     : jarvis encrypt PATH_TO_A_FILE/the_file.txt


Generate Jarvis Private and Public keys
---------------------------------------

Please type : jarvis generate-keys

"""

    print(help)