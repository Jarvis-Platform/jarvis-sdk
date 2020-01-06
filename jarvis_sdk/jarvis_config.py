# -*- coding: utf-8 -*-

import os
import sys
import shutil
import json
from pathlib import Path
from subprocess import check_output
import platform
import ctypes

from jarvis_sdk import jarvis_misc


# Globals
#
_jarvis_rc_file_ = "jarvisrc"
_jarvis_configuration_file_ = "jarvis-configuration.json"
_jarvis_default_parameters_ = {
    "user_email": {
        "name": "Your email address",
        "value": ""
    },
    "jarvis_firebase_api_key": {
        "name": "Jarvis Firebase API key",
        "value": ""
    },
    "jarvis_firebase_auth_domain": {
        "name": "Jarvis Firebase Authentication Domain",
        "value": ""
    },
    "jarvis_api_endpoint": {
        "name": "Jarvis API Endpoint",
        "value": ""
    }
}


def get_jarvis_home():

    # Get host system
    #
    host_system = jarvis_misc.check_platform()

    if (host_system == "Linux") or (host_system == "Darwin"):
        return os.environ["JARVIS_HOME"] + "/"
    elif host_system == "Windows":
        return os.environ["JARVIS_HOME"] + "\\"
    else:
        return None


def set_jarvis_configuration_file(data):

    # Get host system
    #
    host_system = jarvis_misc.check_platform()

    jarvis_configuration_file_full_path = None
    if (host_system == "Linux") or (host_system == "Darwin"):
        jarvis_configuration_file_full_path = os.environ["JARVIS_HOME"] + \
            "/" + _jarvis_configuration_file_
    elif host_system == "Windows":
        jarvis_configuration_file_full_path = os.environ["JARVIS_HOME"] + \
            "\\" + _jarvis_configuration_file_
    else:
        print("Host OS unknown, cannot process Jarvis configuration file.")
        return False

    with open(jarvis_configuration_file_full_path, "w") as f:
        json.dump(data, f)


def get_jarvis_configuration_file(create_if_not_exists=False):

    # Get host system
    #
    host_system = jarvis_misc.check_platform()

    jarvis_configuration_file_full_path = None
    if (host_system == "Linux") or (host_system == "Darwin"):
        jarvis_configuration_file_full_path = os.environ["JARVIS_HOME"] + \
            "/" + _jarvis_configuration_file_
    elif host_system == "Windows":
        jarvis_configuration_file_full_path = os.environ["JARVIS_HOME"] + \
            "\\" + _jarvis_configuration_file_
    else:
        print("Host OS unknown, cannot process Jarvis configuration file.")
        return False

    # Check that file exists
    #
    if (os.path.isfile(jarvis_configuration_file_full_path) is False) and (create_if_not_exists is True):

        # Create file
        #
        with open(jarvis_configuration_file_full_path, "w") as f:
            print("Creating %s" % jarvis_configuration_file_full_path)
            f.write("{}\n")

    # Read/write file content
    #
    read_configuration = None
    try:
        with open(jarvis_configuration_file_full_path, "r") as f:
            read_configuration = json.load(f)
    except Exception as ex:
        print("Error during configuration reading/parsing.")
        print(ex)

    return read_configuration


def check_administrator(host_system):

    print("Checking if we run in ROOT / ADMINISTRATOR mode...")

    if (host_system == "Darwin") or (host_system == "Linux"):

        if os.getuid() == 0:

            # You are ROOT
            print("ERROR : Please DO NOT run install as ROOT. Exiting")
            return True
        else:
            return False

    elif (host_system == "Windows"):

        if ctypes.windll.shell32.IsUserAnAdmin() != 0:
            return False
        else:
            # ADMIN privileges
            #
            print("WARNING : you are running this script with ADMINISTRATOR privileges.")
            # return True

            # Under Windows, it's ok ...
            return False

    else:

        print("Host system unknown, assuming you are not ROOT / ADMIN")
        return False


def process_jarvis_home_directory(host_system):

    jarvis_homedir_suffix = None

    if (host_system == "Linux") or (host_system == "Darwin"):
        print("Processing Jarvis Home directory for Mac OS X / Linux ...")
        jarvis_homedir_suffix = "/.jarvis-home"
    elif host_system == "Windows":
        print("Processing Jarvis Home directory for Windows OS ...")
        jarvis_homedir_suffix = "\AppData\Local\jarvis-home"
    else:
        print("Host OS unknown, cannot process Jarvis Home directory")
        return None

    # Check if directory exists, create it if needed
    #
    jarvis_homedir = str(Path.home()) + jarvis_homedir_suffix
    if os.path.exists(jarvis_homedir) is True:
        print("Jarvis home directory found : " + jarvis_homedir)
        return jarvis_homedir
    else:
        # Create directory
        #
        try:
            os.mkdir(jarvis_homedir)
        except OSError:
            print("Creation of the directory %s failed" % jarvis_homedir)
            return None
        else:
            print("Successfully created the directory %s " % jarvis_homedir)
            return jarvis_homedir


def process_jarvis_home_env_variable(host_system):

    if (host_system == "Linux") or (host_system == "Darwin"):
        print("Processing Jarvis Home directory for Mac OS X / Linux ...")

        user_rc_file = None
        if host_system == "Linux":
            user_rc_file = ".bashrc"
        elif host_system == "Darwin":
            user_rc_file = ".bash_profile"

        # Home directory
        #
        user_rc_file_full_path = (
            os.getenv("HOME")).strip() + "/" + user_rc_file
        print("User RC file : %s" % user_rc_file_full_path)

        # Check that file exists
        #
        if os.path.isfile(user_rc_file_full_path) is False:
            print("WARNING : User rc file \"%s\" not found. Let's create it." %
                  user_rc_file_full_path)
            with open(user_rc_file_full_path, "w") as f:
                print("{} successfully created.".format(user_rc_file_full_path))

        # Remove the JARVIS SDK lines
        #
        jarvisrc_file_full_path = os.environ["JARVIS_HOME"] + "/" + _jarvis_rc_file_
        with open(user_rc_file_full_path, "r") as f:
            lines = f.readlines()
        with open(user_rc_file_full_path, "w") as f:
            for line in lines:
                if ("#JARVIS SDK" not in line) and (_jarvis_rc_file_ not in line):
                    f.write(line)

            # Adding the lines
            #
            f.write("#JARVIS SDK\n")
            f.write("if [ -f '" + jarvisrc_file_full_path +
                    "' ]; then . '" + jarvisrc_file_full_path + "'; fi\n")

        # Write "jarvisrc" file
        #
        with open(jarvisrc_file_full_path, "w") as f:
            f.write("export JARVIS_HOME=" + os.environ["JARVIS_HOME"] + "\n")

    elif host_system == "Windows":
        print("Processing Jarvis Home environment variable for Windows OS ...")

        windows_set_env_variable = "setx JARVIS_HOME \"" + os.environ["JARVIS_HOME"] + "\""
        check_output(windows_set_env_variable, shell=True)

    else:
        print("Host OS unknown, cannot process Jarvis Home environment variable.")
        return False

    return True


def process_configuration_file(host_system):

    read_configuration = get_jarvis_configuration_file(create_if_not_exists=True)

    if read_configuration is None:
        return False

    # Going through default parameters
    #
    print()
    for key in _jarvis_default_parameters_.keys():

        built_message = "Please provide " + \
            _jarvis_default_parameters_[key]["name"] + \
            ". Actual/default value => %s : "

        actual_or_default_value = None
        value_if_empty = None
        try:
            actual_or_default_value = read_configuration[key]
            value_if_empty = read_configuration[key]
        except KeyError:
            actual_or_default_value = _jarvis_default_parameters_[key]["value"]
            value_if_empty = _jarvis_default_parameters_[key]["value"]

        # Display request to the user
        #
        print(built_message % actual_or_default_value, end='', flush=True)

        # Get user value
        #
        user_value = input()

        if not user_value:
            # If the user just hit enter, we'll use the actual/default value
            #
            read_configuration[key] = value_if_empty
        else:
            read_configuration[key] = user_value

    # Write file out
    #
    set_jarvis_configuration_file(read_configuration)

    return True


def jarvis_config():

    print("Installing Jarvis SDK ...")

    # Step 1 : check platform
    #
    host_system = jarvis_misc.check_platform(print_infos=True)

    # Step 2 : check SUDO / ADMINISTRATOR execution
    # Darwin, Linux, Windows, ...
    #
    if check_administrator(host_system) is True:
        return False

    # Step 3 : manage "jarvis sdk" directory
    #
    jarvis_home_directory = process_jarvis_home_directory(host_system)

    # Set temporarly the env. variable
    #
    os.environ["JARVIS_HOME"] = jarvis_home_directory

    if jarvis_home_directory is None:
        print("ERROR while processing Jarvis home directory. Please check console output. Exiting.")
        return False

    # Step 4 : manage JARVIS_HOME environment variable
    #
    if process_jarvis_home_env_variable(host_system) is not True:
        print("ERROR while processing Jarvis home environment variable. Please check console output. Exiting.")
        return False

    # Step 5 : create/update configuration file
    #
    if process_configuration_file(host_system) is False:
        print("Error while creating/upgrading configuration file.")

    # Final step
    #
    print("\nJarvis SDK installation is now complete. Please exit and re-launch your terminal.\n")

    return True
