# -*- coding: utf-8 -*-

import os
import sys
import requests
import base64

import shutil
import json
from pathlib import Path
from subprocess import check_output
import platform
import ctypes

from jarvis_sdk import jarvis_config
from jarvis_sdk import jarvis_auth
from jarvis_sdk import jarvis_misc


def display_configuration_help(command, jarvis_configuration, firebase_user):

    try:

        # Get UID
        #
        uid = firebase_user["userId"]

        url = jarvis_configuration["jarvis_api_endpoint"] + "configuration/v2/help"

        data = {
            "payload": {
                "resource_type" : "help",
                "resource": command + "_help"
            }
        }

        headers = {
            "Content-type": "application/json",
            "Authorization": "Bearer " + firebase_user["idToken"]
        }

        r = requests.post(url, headers=headers, data=json.dumps(data))

        if r.status_code != 200:
            print("\nError : %s\n" % str(r.content, "utf-8"))
        else:
            response = r.json()
            print(response["payload"]["help"])

    except Exception as ex:
        print("Error while trying to contact Jarvis API ...")
        print(ex)
        return False

    return True


def process_sql_query(read_configuration, input_conf_file):

    # Get path
    #
    filepath = os.path.dirname(input_conf_file)
    print("File path : {}".format(filepath))

    # Read associated SQL file
    #
    host_system = jarvis_misc.check_platform()

    path_element = None
    if (host_system == "Linux") or (host_system == "Darwin"):
        path_element = "/"
    elif host_system == "Windows":
        path_element = "\\"
    else:
        print("Host OS unknown, cannot process SQL file reading.")
        return None

    if (filepath is None) or (filepath == ""):
        sql_full_filename = read_configuration["sql_file"]
    else:
        sql_full_filename = filepath + path_element + read_configuration["sql_file"]

    print("SQL file path : {}".format(sql_full_filename))

    try:
        with open(sql_full_filename, "r") as f:
            read_sql_file = f.read()
    except Exception as ex:
        print("Error while reading SQL file : " + ex)
        return None

    # Convert SQL query into Base64
    #
    read_sql_file = bytes(read_sql_file, "utf-8")
    return str(base64.b64encode(read_sql_file), "utf-8")


def process_configuration_file(input_conf_file):

    # Check if the file exists
    #
    if os.path.isfile(input_conf_file) is False:
        print("File \"%s\" does not exists." % input_conf_file)
        return False

    # Read file and parse it as JSON
    #
    read_configuration = None
    try:
        with open(input_conf_file, "r") as f:
            read_configuration = json.load(f)
    except Exception as ex:
        print("Error while parsing configuration file.")
        return False

    # Get global path of the configuration file
    #
    configuration_absolute_pathname = jarvis_misc.get_path_from_file(input_conf_file)

    # Special processing for "table-to-storage"
    #
    if read_configuration["configuration_type"] == "table-to-storage":
        sql_query = process_sql_query(read_configuration, input_conf_file)
        if sql_query is None:
            return False

        read_configuration["sql"] = sql_query

    # Special processing for "storage-to-tables"
    #
    elif read_configuration["configuration_type"] == "storage-to-tables":

        # Process global Markdown file
        #
        try:
            doc_md = configuration_absolute_pathname + read_configuration["doc_md"]
            print("Global Markdown file provided : {}".format(doc_md))
            try:
                with open(doc_md, "r") as f:
                    read_md_file = f.read()
                    read_md_file = bytes(read_md_file, "utf-8")
                    read_configuration["doc_md"] = str(base64.b64encode(read_md_file), "utf-8")

            except Exception as ex:
                print("Error while reading Markdown file : " + ex)
                return None


        except KeyError:
            print("No global Markdown file provided. Continuing ...")

        # Process Destination
        #
        try:
            for destination in read_configuration["destinations"]:

                for table in destination["tables"]:

                    # Process DDL file
                    # mandatory
                    ddl_file = configuration_absolute_pathname + table["ddl_file"]
                    print("Processing DDL file : {}".format(ddl_file))
                    with open(ddl_file, "r") as f:
                        read_ddl_file = f.read()
                        read_ddl_file = bytes(read_ddl_file, "utf-8")
                        table["ddl_infos"] = str(base64.b64encode(read_ddl_file), "utf-8")

                    # Process Markdown file
                    # optional
                    try:
                        doc_md = configuration_absolute_pathname + table["doc_md"]
                        print("Processing table Markdown file : {}".format(doc_md))
                        with open(doc_md, "r") as f:
                            read_doc_md = f.read()
                            read_doc_md = bytes(read_doc_md, "utf-8")
                            table["doc_md"] = str(base64.b64encode(read_doc_md), "utf-8")
                    except Exception as ex:
                        print("Cannot process table Markdown file. Continuing ... : {}".format(ex))

        except Exception as ex:
            print("Error while processing destinations / tables : {}".format(ex))
            return False

    return read_configuration


def check_configuration(input_conf_file=None, jarvis_configuration=None, firebase_user=None):

    # Process configuration file
    #
    read_configuration = process_configuration_file(input_conf_file)

    # Call API
    #
    try:

        url = jarvis_configuration["jarvis_api_endpoint"] + "configuration/v2"
        data = {
            "payload": {
                "resource_type" : "check-configuration",
                "resource": read_configuration,
                "uid": firebase_user["userId"]
            }
        }
        headers = {
            "Content-type": "application/json",
            "Authorization": "Bearer " + firebase_user["idToken"]}

        r = requests.post(url, headers=headers, data=json.dumps(data))

        if r.status_code == 404:
            # Special case : if the configuration JSON Schema is not found, we let pass until we can complete the JSON Schema database
            #
            print("\nConfiguration JSON Schema not found in JARVIS Platform.")
            return True
        elif r.status_code != 200:
            print("\nError(s) : \n%s\n" % str(r.content, "utf-8"))
            return False
        else:
            response = r.json()
            print(response["payload"]["message"])
            return True

    except Exception as ex:
        print("Error while trying to contact Jarvis API ...")
        print(ex)
        return False


def get_project_profile_from_configuration(input_conf_file=None, jarvis_configuration=None, firebase_user=None):

    # Process configuration file
    #
    read_configuration = process_configuration_file(input_conf_file)

    # Call API
    #
    try:

        url = jarvis_configuration["jarvis_api_endpoint"] + "configuration/v2"
        data = {
            "payload": {
                "resource_type" : "get-gcp-project-id",
                "resource": read_configuration,
                "uid": firebase_user["userId"]
            }
        }
        headers = {
            "Content-type": "application/json",
            "Authorization": "Bearer " + firebase_user["idToken"]}

        r = requests.post(url, headers=headers, data=json.dumps(data))

        if r.status_code == 404:
            # Not found
            #
            print("\nGCP Project ID not found for your configuration")
            return None

        elif r.status_code != 200:
            print("\nError(s) : \n%s\n" % str(r.content, "utf-8"))
            return None

        else:
            response = r.json()
            return response["payload"]["message"]

    except Exception as ex:
        print("Error while trying to contact Jarvis API ...")
        print(ex)
        return False


def deploy_configuration(input_conf_file, project_profile, jarvis_configuration, firebase_user, no_gcp_cf_deploy):

    # Process configuration file
    #
    read_configuration = process_configuration_file(input_conf_file)

    # Do we need to deploy the associated CF ?
    #
    if no_gcp_cf_deploy is True:
        print("\nThe GCP Cloud Function associated to your configuration WILL NOT be deployed.")
    else:
        print("\nThe GCP Cloud Function associated with your configuration deployment will be deployed if needed.")
        print("Please wait up to 2 minutes for full deployment.")

    # Call API
    #
    try:

        url = jarvis_configuration["jarvis_api_endpoint"] + "configuration/v2"
        data = {
            "payload": {
                "resource": read_configuration,
                "project_profile": project_profile,
                "uid": firebase_user["userId"],
                "deploy_cf" : not no_gcp_cf_deploy
            }
        }
        headers = {
            "Content-type": "application/json",
            "Authorization": "Bearer " + firebase_user["idToken"
                                                       ]}

        r = requests.put(url, headers=headers, data=json.dumps(data))

        if r.status_code != 200:
            print("\nError : %s\n" % str(r.content, "utf-8"))
            return False
        else:
            response = r.json()
            print(response["payload"]["message"])
            return True

    except Exception as ex:
        print("Error while trying to contact Jarvis API ...")
        print(ex)
        return False


def create_configuration(configuration_type, output_file, jarvis_configuration, firebase_user):

    # Some information
    #
    print("Configuration type : {}".format(configuration_type))
    print("Output file        : {}".format(output_file))

    # Call API
    #
    try:

        url = jarvis_configuration["jarvis_api_endpoint"] + "configuration/v2"
        data = {
            "payload": {
                "resource_type" : "configuration-type",
                "resource": configuration_type,
                "uid": firebase_user["userId"]
            }
        }
        headers = {
            "Content-type": "application/json",
            "Authorization": "Bearer " + firebase_user["idToken"
                                                       ]}

        r = requests.post(url, headers=headers, data=json.dumps(data))

        if r.status_code != 200:
            print("\nError : %s\n" % str(r.content, "utf-8"))
            return False
        else:
            response = r.json()
            config = str(base64.b64decode(response["payload"]["content"]), "utf-8")
            with open(output_file, mode='w') as file:
                file.write(config)
            return True

    except Exception as ex:
        print("Error while trying to contact Jarvis API ...")
        print(ex)
        return False


def process(args):

    print("Jarvis Configuration Manager.")

    # Get configuration
    #
    jarvis_configuration = jarvis_config.get_jarvis_configuration_file()

    # Get firebase user
    #
    firebase_user = jarvis_auth.get_refreshed_firebase_user(
        jarvis_configuration)

    if args.command == "deploy":
        if len(args.arguments) >= 2:
            if args.arguments[1] is not None:
                if args.arguments[1] == "help":
                    return display_configuration_help(args.command, jarvis_configuration, firebase_user)
                else:

                    # First, check if the configuration is valid
                    #
                    if check_configuration(input_conf_file=args.arguments[1], jarvis_configuration=jarvis_configuration, firebase_user=firebase_user) is False:
                        return False

                    # Check if GCP Project ID is present
                    #
                    project_profile = get_project_profile_from_configuration(input_conf_file=args.arguments[1], jarvis_configuration=jarvis_configuration, firebase_user=firebase_user)
                    if (project_profile is None) or (project_profile == ""):

                        # Get list of project profiles open to the user and ask him to pick one
                        #
                        ret_code, project_profile = jarvis_misc.choose_project_profiles(jarvis_configuration, firebase_user)
                        if ret_code is False:
                            return False
                    else:
                        print("\nProject profile used : {}\n".format(project_profile))

                    return deploy_configuration(args.arguments[1], project_profile, jarvis_configuration, firebase_user, args.no_gcp_cf_deploy)
            else:
                print("Argument unknown." % args.arguments[1])
                return False
        else:
            return display_configuration_help(args.command, jarvis_configuration, firebase_user)

    elif args.command == "create":
        if len(args.arguments) >= 2:
            if args.arguments[1] is not None:
                if args.arguments[1] == "help":
                    return display_configuration_help(args.command, jarvis_configuration, firebase_user)
                else:
                    
                    # retrieve output_filename
                    #
                    try:
                        output_filename = args.arguments[2]
                    except Exception as ex:
                        output_filename = args.arguments[1] + ".json"

                    return create_configuration(args.arguments[1], output_filename, jarvis_configuration, firebase_user)
            else:
                print("Argument unknown." % args.arguments[1])
                return False
        else:
            return display_configuration_help(args.command, jarvis_configuration, firebase_user)

    elif args.command == "check":   
        if len(args.arguments) >= 2:
            if args.arguments[1] is not None:
                if args.arguments[1] == "help":
                    return display_configuration_help(args.command, jarvis_configuration, firebase_user)
                else:
                    return check_configuration(input_conf_file=args.arguments[1], jarvis_configuration=jarvis_configuration, firebase_user=firebase_user)
            else:
                print("Argument unknown." % args.arguments[1])
                return False
        else:
            return display_configuration_help(args.command, jarvis_configuration, firebase_user)

    return True
