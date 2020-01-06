# -*- coding: utf-8 -*-

import os
import argparse
import datetime
import json
import base64
import pickle
import warnings
import pprint

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
JARVIS_SDK_VERSION="0.0.15"



def display_jarvis_header():

    print("")
    print("*************************************************")
    print("*                                               *")
    print("*      ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗  *")
    print("*      ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝  *")
    print("*      ██║███████║██████╔╝██║   ██║██║███████╗  *")
    print("* ██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║  *")
    print("* ╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║  *")
    print("*  ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝  *")
    print("*                                               *")
    print("*             ███████╗██████╗ ██╗  ██╗          *")
    print("*             ██╔════╝██╔══██╗██║ ██╔╝          *")
    print("*             ███████╗██║  ██║█████╔╝           *")
    print("*             ╚════██║██║  ██║██╔═██╗           *")
    print("*             ███████║██████╔╝██║  ██╗          *")
    print("*             ╚══════╝╚═════╝ ╚═╝  ╚═╝          *")
    print("*                                               *")
    print("*************************************************")
    print("Version : " + JARVIS_SDK_VERSION)
    print("")


def main():

    # Display Jarvis header
    #
    display_jarvis_header()

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("command", help="Jarvis SDK command.", type=str)
    parser.add_argument("--no-gcp-cf-deploy", help="Will not deploy GCP Cloud Function associated to a configuration.", action='store_true')
    parser.add_argument("arguments", nargs=argparse.REMAINDER)

    args = parser.parse_args()

    # Evaluating COMMAND
    #
    if args.command == "config":
        jarvis_config.jarvis_config()

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
                jarvis_configuration_manager.process(args)

    elif args.command == "check":
        if len(args.arguments) > 0:
            if (args.arguments)[0] == "configuration":
                jarvis_configuration_manager.process(args)

    elif args.command == "deploy":
        if len(args.arguments) > 0:
            if (args.arguments)[0] == "configuration":
                jarvis_configuration_manager.process(args)
            if (args.arguments)[0] == "gcp-cloud-function":
                jarvis_gcp_cf_manager.process(args)

    elif args.command == "dag-generator":
        if len(args.arguments) > 0:
            sql_dag_generator.process(args)
        else:
            print("Please provide your DAG configuration file.\n")
    
    elif args.command == "help":
        jarvis_help.display_help()
    else:
        jarvis_help.display_help()




if __name__ == "__main__":
    main()