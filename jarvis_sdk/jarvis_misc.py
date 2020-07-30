# -*- coding: utf-8 -*-

import os
import platform
import requests
import json

from jarvis_sdk import jarvis_project


def check_platform(print_infos=False):

    if print_infos is True:
        print("Checking platform ...")
        print("Platform : " + platform.platform())
        print("System   : " + platform.system())

    return platform.system().strip()


def get_jarvis_worker_groups(
        jarvis_configuration=None,
        firebase_user=None,
        sdk_version=None,
        perform_ssl_verification=True,
        certificate=""):

    # Call API to retrieve Project Profiles accessible by the user
    #
    try:

        url = jarvis_configuration["jarvis_api_endpoint"].rstrip(
            "/") + "/project-management"
        data = {
            "payload": {
                "resource": "get-jarvis-worker-groups",
                "uid": firebase_user["userId"],
                "sdk_version": sdk_version
            }
        }
        headers = {
            "Content-type": "application/json",
            "Authorization": "Bearer " + firebase_user["idToken"]}

        r = requests.post(url, headers=headers, data=json.dumps(
            data), cert=certificate, verify=perform_ssl_verification)

        if r.status_code != 200:
            print("\nError : {}\n".format(str(r.content, "utf-8")))
            return False, None
        else:
            response = r.json()
            return True, response["payload"]["message"]

    except Exception as ex:
        print("Error while trying to contact Jarvis API ...")
        print(ex)
        return False, None


def get_jarvis_worker_group_environments(
        jarvis_configuration=None,
        firebase_user=None,
        group=None,
        sdk_version=None,
        perform_ssl_verification=True,
        certificate=""):

    # Call API to retrieve Project Profiles accessible by the user
    #
    try:

        url = jarvis_configuration["jarvis_api_endpoint"].rstrip(
            "/") + "/project-management"
        data = {
            "payload": {
                "resource": "get-jarvis-worker-group-environments",
                "group": group.strip(),
                "uid": firebase_user["userId"],
                "sdk_version": sdk_version
            }
        }
        headers = {
            "Content-type": "application/json",
            "Authorization": "Bearer " + firebase_user["idToken"]}

        r = requests.post(url, headers=headers, data=json.dumps(
            data), cert=certificate, verify=perform_ssl_verification)

        if r.status_code != 200:
            print("\nError : {}\n".format(str(r.content, "utf-8")))
            return False, None
        else:
            response = r.json()
            return True, response["payload"]["message"]

    except Exception as ex:
        print("Error while trying to contact Jarvis API ...")
        print(ex)
        return False, None


def get_project_profiles(jarvis_configuration, firebase_user):

    # Call API to retrieve Project Profiles accessible by the user
    #
    try:

        url = jarvis_configuration["jarvis_api_endpoint"] + "project-profile"
        data = {
            "payload": {
                "uid": firebase_user["userId"]
            }
        }
        headers = {
            "Content-type": "application/json",
            "Authorization": "Bearer " + firebase_user["idToken"]}

        r = requests.post(url, headers=headers, data=json.dumps(
            data), verify=jarvis_configuration["perform_ssl_verification"])

        if r.status_code != 200:
            print("\nError : %s\n" % str(r.content, "utf-8"))
            return False, None
        else:
            response = r.json()
            return True, response["payload"]["message"]

    except Exception as ex:
        print("Error while trying to contact Jarvis API ...")
        print(ex)
        return False, None


def choose_project_profiles(jarvis_configuration, firebase_user):

    ret_code, payload = get_project_profiles(
        jarvis_configuration, firebase_user)

    if ret_code is False:
        return False, None

    # Display available profiles for the user
    #
    print("")
    print("List of available profiles for you :")
    print("-----------------------------------")
    index = 1

    payload.sort()

    for profile in payload:

        print("{} - {}".format(str(index), profile))
        index += 1
    print("")

    # Ask the user to pick one
    #
    while True:
        print("Please choose a profile by typing its number : ", end='', flush=True)
        user_value = input()

        try:
            user_value = int(user_value)
        except Exception as ex:
            continue

        if (user_value <= len(payload)) and (user_value >= 1):
            break

        continue

    # Infos
    #
    choice = payload[user_value - 1]
    print("\nYou choosed to use profile : {}\n".format(choice))

    return True, choice


def get_path_from_file(input_file):

    # Get path
    #
    filepath = os.path.dirname(input_file)

    host_system = check_platform()

    path_element = None
    if (host_system == "Linux") or (host_system == "Darwin"):
        path_element = "/"
    elif host_system == "Windows":
        path_element = "\\"
    else:
        print("Host OS unknown, cannot process path from file.")
        return None

    if (filepath is None) or (filepath == ""):
        return ""
    else:
        return (filepath + path_element)


def get_argument_from_command_line(arguments=None, arg=None):

    if (arguments is None) or (arg is None):
        return None

    try:
        for input_arg in arguments:
            if arg in input_arg:
                return input_arg.split("=")[1]
    except Exception as ex:
        print("Error while parsing command line arguments. Please check your entry.\n{}\n".format(ex))
        return None

    return None


def project_picker(configuration=None, arguments=None):

    if (arguments is None) or (configuration is None):
        return None

    # Let's check if the Jarvis Master Project has been set on the command line
    #
    project = get_argument_from_command_line(
        arguments=arguments, arg="--jarvis-master-project=")
    project = jarvis_project.project_exists(
        configuration=configuration, project=project)

    if project is None:
        # Select a project
        #
        return jarvis_project.select_project(configuration=configuration)

    return project
