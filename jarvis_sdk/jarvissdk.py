# -*- coding: utf-8 -*-

import os
import argparse
import datetime
import json
import base64
import pickle
import warnings
import pprint

from pkg_info import get_pkg_info
from semver import compare

from jarvis_sdk import jarvis_config
from jarvis_sdk import jarvis_configuration_manager
from jarvis_sdk import jarvis_gcp_cf_manager
from jarvis_sdk import jarvis_auth
from jarvis_sdk import jarvis_help
from jarvis_sdk import jarvis_crypto
from jarvis_sdk import sql_dag_generator

import google.auth

warnings.filterwarnings(
    "ignore", "Your application has authenticated using end user credentials")

# Globals
#
__version__ = "1.1.4"
JARVIS_SDK_VERSION=__version__
JARVIS_SDK_NAME="jarvis-sdk"



def display_jarvis_header():

    print("")
    print("JARVIS SDK")
    print("Version : " + JARVIS_SDK_VERSION)
    print("")


def notify_update_jarvis_sdk():

    try:
    
        pkg = get_pkg_info(JARVIS_SDK_NAME)

        if compare(__version__, pkg.version) < 0:

            print("\nIMPORTANT NOTICE")
            print("-----------------")
            print("Update available {} -> {}".format(__version__, pkg.version))
            print("Please run : pip3 install jarvis-sdk --upgrade\n")
    
    except Exception as ex:

        print("\nError while retrieving package information : \n{}\n".format(ex))
    

def main():

    # Display Jarvis header
    #
    display_jarvis_header()  

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("command", help="Jarvis SDK command.", type=str)
    parser.add_argument("--no-gcp-cf-deploy", help="Will not deploy GCP Cloud Function associated to a configuration.", action='store_true')
    parser.add_argument("arguments", nargs=argparse.REMAINDER)

    args = parser.parse_args()

    # Evaluating COMMAND
    #
    if args.command == "config":
        jarvis_config.jarvis_config()

    elif args.command == "configuration":

        # TTT local run case
        #
        conf_usage = "Usage :\n\njarvis configuration run TTT-CONFIGURATION.json [task_1 task_2 ... task_N]\n\n"

        if len(args.arguments) >= 2:
            if args.arguments[0].strip() == "run":
                sql_dag_generator.process(configuration_file=args.arguments[1], run_locally=True, arguments=args.arguments, jarvis_sdk_version=JARVIS_SDK_VERSION)
            else:
                print(conf_usage)
        else:
            print(conf_usage)

    elif args.command == "encrypt":
        if len(args.arguments) > 0:
            jarvis_crypto.encrypt_payload(args.arguments[0])
        else:
            print("Please provide something to encrypt.")

    elif args.command == "generate-keys":
        jarvis_crypto.generate_key_pair()

    elif args.command == "auth":
        if len(args.arguments) > 0:
            if (args.arguments)[0] == "login":
                jarvis_auth.login()

    elif args.command == "create":
        if len(args.arguments) > 0:
            if (args.arguments)[0] == "configuration":
                jarvis_configuration_manager.process(args, jarvis_sdk_version=JARVIS_SDK_VERSION)

    elif args.command == "check":
        if len(args.arguments) > 0:
            if (args.arguments)[0] == "configuration":
                jarvis_configuration_manager.process(args, jarvis_sdk_version=JARVIS_SDK_VERSION)

    elif args.command == "deploy":
        if len(args.arguments) > 0:
            if (args.arguments)[0] == "configuration":
                jarvis_configuration_manager.process(args, jarvis_sdk_version=JARVIS_SDK_VERSION)
            if (args.arguments)[0] == "gcp-cloud-function":
                jarvis_gcp_cf_manager.process(args)
    
    elif args.command == "help":
        jarvis_help.display_help()
    else:
        jarvis_help.display_help()

    # Check if there is a newer version
    #
    notify_update_jarvis_sdk()


if __name__ == "__main__":
    main()
