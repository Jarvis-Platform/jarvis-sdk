# -*- coding: utf-8 -*-

import base64
import json
import os

from jarvis_sdk import jarvis_config


def display_help():

    print("jarvis project help")
    print("-------------------\n")


def project_exists(configuration=None, project=None):

    if (configuration is None) or (project is None):
        return None

    try:
        if project in configuration["jarvis_master_projects"].keys():
            return project
        else:
            print("\nWARNING : \"{}\" has not been found in your Jarvis Master Project list.\n".format(project))
            return None
    except Exception as ex:
        print("Error while checking existence of {}.\n{}\n".format(project, ex))
        return None


def select_project(configuration=None):

    if configuration is None:
        configuration = jarvis_config.get_jarvis_configuration_file()

        if configuration is None:
            return None

    # First, we check if there is a default project set in the configuration
    #
    # TODO
    #
    # try:
    #     if configuration["common"]["jarvis_master_project_id"] not in (None, ""):
    #         print("Default Jarvis Project Manager : {}\n".format(configuration["common"]["jarvis_master_project_id"]))
    #         return configuration["common"]["jarvis_master_project_id"]
    #     else:
    #         raise Exception("jarvis_master_project_id not found.")
    # except Exception:
    #     print("Default Jarvis Master Project does not seem to be set. Run \"jarvis project set\" to do so\n.")

    print("List of Jarvis Master Projects")
    print("------------------------------\n")

    project_ids = sorted(configuration["jarvis_master_projects"].keys())
    index = 1
    for id in project_ids:

        print(str(index) + " - " + id)
        index += 1

    print()

    while True:
        print("Please select a Jarvis Master Project : ", end='', flush=True)
        try:
            user_value = int(input())
            if (user_value < 1) or (user_value > index):
                continue

            else:
                print("Default Jarvis Project Manager : {}\n".format(project_ids[user_value-1]))
                return project_ids[user_value-1]
        except Exception:
            continue


def list_projects():

    read_configuration=jarvis_config.get_jarvis_configuration_file()

    if read_configuration is None:
        return False

    print("List of Jarvis Master Projects")
    print("------------------------------\n")

    index=1
    for project_id in sorted(read_configuration["jarvis_master_projects"].keys()):

        print(str(index) + " - " + project_id)
        index += 1

    print()


def add_project():

    read_configuration=jarvis_config.get_jarvis_configuration_file()

    if read_configuration is None:
        return False

    # Add a new Jarvis Master Project
    #
    print("Please provide the GCP Project ID of the Jarvis Master Project : ",
          end='', flush=True)
    jm_gcp_project_id=input().strip()
    print("Please provide the Firebase API key : ", end='', flush=True)
    jm_firebase_api_key=input().strip()
    print("Please provide the Firebase Authentication Domain : ", end='', flush=True)
    jm_firebase_auth_domain=input().strip()
    print("Please provide the Jarvis API Endpoint address : ", end='', flush=True)
    jm_api_endpoint=input().strip()

    # Email
    #
    try:
        user_email=read_configuration["common"]["user_email"]
    except KeyError:
        user_email=None

    print("Please provide the default user email. Actual value => {} : ".format(
        user_email), end='', flush=True)
    user_value=input()

    if user_value:
        user_email=user_value

    # Let's save it all
    #
    read_configuration["jarvis_master_projects"][jm_gcp_project_id]={}
    read_configuration["jarvis_master_projects"][jm_gcp_project_id]["jarvis_master_gcp_project_id"]=jm_gcp_project_id
    read_configuration["jarvis_master_projects"][jm_gcp_project_id]["jarvis_firebase_api_key"]=jm_firebase_api_key
    read_configuration["jarvis_master_projects"][jm_gcp_project_id]["jarvis_firebase_auth_domain"]=jm_firebase_auth_domain
    read_configuration["jarvis_master_projects"][jm_gcp_project_id]["jarvis_api_endpoint"]=jm_api_endpoint
    read_configuration["jarvis_master_projects"][jm_gcp_project_id]["user_email"]=user_email

    jarvis_config.set_jarvis_configuration_file(read_configuration)

    print("Jarvis Master Project saved : {}\n".format(jm_gcp_project_id))


def set_project(jarvis_master_project_id=None):

    read_configuration=jarvis_config.get_jarvis_configuration_file()

    if read_configuration is None:
        return False

    project_ids=sorted(read_configuration["jarvis_master_projects"].keys())

    if len(project_ids) <= 0:
        print("There is no Jarvis Master Project setup. Please add at least one.")
        return True

    # Check if the user specified a project id
    #
    if jarvis_master_project_id is not None:
        if jarvis_master_project_id in project_ids:
            read_configuration["common"]["jarvis_master_project_id"]=jarvis_master_project_id
            jarvis_config.set_jarvis_configuration_file(read_configuration)
            print("Default Jarvis Master Project set : {}\n".format(
                jarvis_master_project_id))
            return True
        else:
            print("The Jarvis Master Project Id provided ({}) does not exist in your configuration. Please add it.\n".format(
                jarvis_master_project_id))
            return True

    print("List of Jarvis Master Projects")
    print("------------------------------\n")

    index=1
    for id in project_ids:

        print(str(index) + " - " + id)
        index += 1

    print()

    while True:
        print("Please select default Jarvis Master Project : ", end='', flush=True)
        try:
            user_value=int(input())
            if (user_value < 1) or (user_value > index):
                continue

            else:
                read_configuration["common"]["jarvis_master_project_id"]=project_ids[user_value-1]
                jarvis_config.set_jarvis_configuration_file(read_configuration)
                print("Default Jarvis Master Project set : {}\n".format(
                    project_ids[user_value-1]))
                return True

        except Exception:
            continue


def delete_project(jarvis_master_project_id=None):

    read_configuration=jarvis_config.get_jarvis_configuration_file()

    if read_configuration is None:
        return False

    project_ids=sorted(read_configuration["jarvis_master_projects"].keys())

    if len(project_ids) <= 0:
        print("There is no Jarvis Master Project setup. Please add at least one.")
        return True

    # Check if the user specified a project id
    #
    if jarvis_master_project_id is not None:
        if jarvis_master_project_id in project_ids:
            while True:
                print("Do you confirm that you want to delete {} ? y/n : ".format(
                    jarvis_master_project_id), end='', flush=True)
                user_value=input()
                if user_value == "y":
                    del read_configuration["jarvis_master_projects"][jarvis_master_project_id]
                    jarvis_config.set_jarvis_configuration_file(
                        read_configuration)
                    print("Jarvis Master Project deleted : {}\n".format(
                        jarvis_master_project_id))
                    break
                elif user_value == "n":
                    break
                else:
                    continue

            return True
        else:
            print("The Jarvis Master Project Id provided ({}) does not exist in your configuration.\n".format(
                jarvis_master_project_id))
            return True

    print("List of Jarvis Master Projects")
    print("------------------------------\n")

    index=1
    for id in project_ids:

        print(str(index) + " - " + id)
        index += 1

    print()

    while True:
        print("Please select default Jarvis Master Project : ", end='', flush=True)
        try:
            user_value=int(input())
            if (user_value < 1) or (user_value > index):
                continue

            else:
                del read_configuration["jarvis_master_projects"][project_ids[user_value-1]]
                jarvis_config.set_jarvis_configuration_file(read_configuration)
                print("Jarvis Master Project deleted : {}\n".format(
                    project_ids[user_value-1]))
                return True

        except Exception:
            continue


def edit_project():

    read_configuration=jarvis_config.get_jarvis_configuration_file()

    if read_configuration is None:
        return False

    project_ids=sorted(read_configuration["jarvis_master_projects"].keys())

    if len(project_ids) <= 0:
        print("There is no Jarvis Master Project setup. Please add at least one.")
        return True

    print("List of Jarvis Master Projects")
    print("------------------------------\n")

    index=1
    for id in project_ids:

        print(str(index) + " - " + id)
        index += 1

    print()

    while True:
        print("Please select a Jarvis Master Project to edit: ", end='', flush=True)
        try:
            user_value=int(input())
            if (user_value < 1) or (user_value > index):
                continue

            else:

                # Edit the project
                #
                project=read_configuration["jarvis_master_projects"][project_ids[user_value-1]]

                # Save firebase_user if present
                #
                try:
                    firebase_user=project["firebase_user"]
                except Exception:
                    firebase_user=None

                # Delete current configuration
                #
                del read_configuration["jarvis_master_projects"][project_ids[user_value-1]]

                jm_gcp_project_id=project["jarvis_master_gcp_project_id"]
                print("Please provide the GCP Project ID of the Jarvis Master Project. Current value -> {} : ".format(
                    jm_gcp_project_id), end='', flush=True)
                user_value=input().strip()
                if user_value:
                    jm_gcp_project_id=user_value

                jm_firebase_api_key=project["jarvis_firebase_api_key"]
                print("Please provide the Firebase API key. Current value -> {} : ".format(
                    jm_firebase_api_key), end='', flush=True)
                user_value=input().strip()
                if user_value:
                    jm_firebase_api_key=user_value

                jm_firebase_auth_domain=project["jarvis_firebase_auth_domain"]
                print("Please provide the Firebase Authentication Domain. Current value -> {} : ".format(
                    jm_firebase_auth_domain), end='', flush=True)
                user_value=input().strip()
                if user_value:
                    jm_firebase_auth_domain=user_value

                jm_api_endpoint=project["jarvis_api_endpoint"]
                print("Please provide the Jarvis API Endpoint address. Current value -> {} : ".format(
                    jm_api_endpoint), end='', flush=True)
                user_value=input().strip()
                if user_value:
                    jm_api_endpoint=user_value

                user_email=project["user_email"]
                print("Please provide your email address. Current value -> {} : ".format(
                    user_email), end='', flush=True)
                user_value=input().strip()
                if user_value:
                    user_email=user_value

                # Let's save it all
                #
                read_configuration["jarvis_master_projects"][jm_gcp_project_id]={
                    }
                read_configuration["jarvis_master_projects"][jm_gcp_project_id]["jarvis_master_gcp_project_id"]=jm_gcp_project_id
                read_configuration["jarvis_master_projects"][jm_gcp_project_id]["jarvis_firebase_api_key"]=jm_firebase_api_key
                read_configuration["jarvis_master_projects"][jm_gcp_project_id]["jarvis_firebase_auth_domain"]=jm_firebase_auth_domain
                read_configuration["jarvis_master_projects"][jm_gcp_project_id]["jarvis_api_endpoint"]=jm_api_endpoint
                read_configuration["jarvis_master_projects"][jm_gcp_project_id]["user_email"]=user_email
                read_configuration["jarvis_master_projects"][jm_gcp_project_id]["firebase_user"]=firebase_user

                jarvis_config.set_jarvis_configuration_file(read_configuration)

                print("Jarvis Master Project saved : {}\n".format(
                    jm_gcp_project_id))

                break

        except Exception:
            continue

    return True

def process(arguments):

    if (arguments is None) or (len(arguments) <= 0):
        display_help()
        return

    if arguments[0].strip() == "list":
        list_projects()
    elif arguments[0].strip() == "add":
        add_project()
    elif arguments[0].strip() == "edit":
        edit_project()
    elif arguments[0].strip() == "set":
        if len(arguments) >= 2:
            set_project(jarvis_master_project_id=arguments[1].strip())
        else:
            set_project()
    elif arguments[0].strip() == "delete":
        if len(arguments) >= 2:
            delete_project(jarvis_master_project_id=arguments[1].strip())
        else:
            delete_project()
    else:
        display_help()

    return
