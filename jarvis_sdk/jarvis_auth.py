# -*- coding: utf-8 -*-

import os
import json
import requests
import getpass

from firebase import Firebase

from jarvis_sdk import jarvis_config


def get_firebase_configuration(read_configuration):

    # Check if we have Jarvis Firebase information
    #
    try:
        return {
            "apiKey": read_configuration["jarvis_firebase_api_key"],
            "authDomain": read_configuration["jarvis_firebase_auth_domain"],
            "databaseURL": "",
            "storageBucket": ""
        }
    except KeyError as ex:
        print("Error while retrieving Jarvis Firebase parameter : \n%s" % ex)
        return None


def get_firebase_user(read_configuration):

    # Check if we have Jarvis Firebase user in configuration file
    #
    try:
        return read_configuration["firebase_user"]
    except KeyError as ex:
        print("Error while retrieving Jarvis Firebase user : \n%s" % ex)
        return None


def get_refreshed_firebase_user(read_configuration):

    # Instantiate service
    #
    firebase = Firebase(get_firebase_configuration(read_configuration))

    # Get Firebase AUTH service
    #
    auth = firebase.auth()

    # Get current user
    #
    firebase_user = get_firebase_user(read_configuration)
    if firebase_user is not None:
        try:
            firebase_user = auth.refresh(firebase_user['refreshToken'])
            return firebase_user
        except Exception as ex:
            print("Error while refreshing user's access token : %s" % ex)
            return None
    else:
        return None

    
def login():

    # Check if we already have user data in JARVIS_HOME configuration file
    #
    read_configuration = jarvis_config.get_jarvis_configuration_file()
    if read_configuration is None:
        print("No configuration file found in your Jarvis Home directory...")
        print("Please run \"jarvis config\" to make sure Jarvis SDK is properly configured.")
        return False

    # Check if we have Jarvis Firebase information
    #
    jarvis_firebase_config = get_firebase_configuration(read_configuration)
    if jarvis_firebase_config is None:
        return False

    # Instantiate service
    #
    firebase = Firebase(jarvis_firebase_config)

    # Get Firebase AUTH service
    #
    auth = firebase.auth()

    # Try to authenticate
    #
    firebase_user = None

    # Ask user info to authenticate through firebase
    #
    print("Please provide your email address. Default -> " +
            read_configuration["user_email"] + " : ", end='', flush=True)
    user_email = input().strip()
    if not user_email:
        user_email = read_configuration["user_email"]

    user_password = getpass.getpass("Please provide your password : ")

    email_not_found = False

    try:
        firebase_user = auth.sign_in_with_email_and_password(user_email, user_password)
    except requests.exceptions.HTTPError as ex:
        if ex.strerror is not None:
            error = (json.loads(ex.strerror)["error"]["message"]).strip()

            if error == "INVALID_EMAIL":
                print("The user email address provided is invalid/malformed.")
                return False

            elif error == "EMAIL_NOT_FOUND":
                print("The user \"" + user_email + "\" does not exists in Jarvis database.")
                email_not_found = True

            elif error == "INVALID_PASSWORD":
                print("The password provided is invalid")
                return False
            else:
                print("Error unknown : \n%s" % ex.strerror)
                return False
                    
    # Create user if needed
    #
    if email_not_found is True:
        while True:
            print("Do you want to create the account \"" + user_email + "\" on Jarvis Platform ? y/n : ", end='', flush=True)
            user_entry = input().strip()
            if user_entry == "n":
                return True
            elif user_entry == "y":

                # Get a password
                #
                while True:
                    user_password = getpass.getpass("Please provide a password : ")
                    user_password_2 = getpass.getpass("Please retype your password : ")
                    if user_password != user_password_2:
                        print("The password you retyped is different from the first one, please retry ...")
                    else:
                        break

                # Try to create users
                #
                try:
                    firebase_user = auth.create_user_with_email_and_password(user_email, user_password)
                    auth.send_email_verification(firebase_user['idToken'])
                    print("\nThe account \"" + user_email + "\" has been created successfully.")
                    print("Please check your email address to validate your account creation.\n")

                except Exception as ex:
                    print("An error occurred while attempting to create a new user.")
                    print(ex)
                break

    # Save user in configuration file
    #
    print("Saving configuration ...")
    read_configuration["firebase_user"] = firebase_user
    jarvis_config.set_jarvis_configuration_file(read_configuration)

    return True