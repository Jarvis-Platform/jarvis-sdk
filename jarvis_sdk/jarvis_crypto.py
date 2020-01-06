# -*- coding: utf-8 -*-

import base64
import json
import os

from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes
from Crypto.Cipher import AES, PKCS1_OAEP

from jarvis_sdk import jarvis_config


# Globals
#
JARVIS_PRIVATE_KEY = "jarvis_private_key.pem"
JARVIS_PUBLIC_KEY = "jarvis_public_key.pem"


def generate_key_pair():

    jarvis_home_path = jarvis_config.get_jarvis_home()

    key = RSA.generate(2048)
    private_key = key.export_key()
    privatekey_filename = jarvis_home_path + JARVIS_PRIVATE_KEY
    file_out = open(privatekey_filename, "wb")
    file_out.write(private_key)
    print("JARVIS Private key generated : %s" % privatekey_filename)

    public_key = key.publickey().export_key()
    publickey_filename = jarvis_home_path + JARVIS_PUBLIC_KEY
    file_out = open(publickey_filename, "wb")
    file_out.write(public_key)
    print("JARVIS Public key generated : %s" % publickey_filename)


def encrypt_payload(payload):

    # Check if payload is a file
    #
    try:
        if os.path.isfile(payload) is True:
            with open(payload, "r")as file:
                payload = file.read()
    except Exception as ex:
        print(ex)


    # Get JARVIS Home path
    #
    jarvis_home_path = jarvis_config.get_jarvis_home()

    # Public Key
    #
    public_key_path = jarvis_home_path + JARVIS_PUBLIC_KEY
    print("JARVIS Public key : " + public_key_path)
    public_key = RSA.import_key(open(public_key_path).read())

    # Convert MESSAGE to base64
    #
    base64_message = base64.b64encode((payload).encode('utf-8'))
    # print("Message         : " + payload)
    # print("BASE 64 message : " + str(base64_message))

    # Encrypt DATA
    #
    session_key = get_random_bytes(16)
    cipher_aes = AES.new(session_key, AES.MODE_EAX)

    # Encrypt the session key with the public RSA key
    cipher_rsa = PKCS1_OAEP.new(public_key)

    # Encrypt the data with the AES session key
    ciphertext, tag = cipher_aes.encrypt_and_digest(base64_message)
    enc_session_key = (cipher_rsa.encrypt(session_key))

    output_data = {}
    output_data["cipher_aes"] = cipher_aes.nonce.hex()
    output_data["tag"] = tag.hex()
    output_data["ciphertext"] = ciphertext.hex()
    output_data["enc_session_key"] = enc_session_key.hex()

    print("\n\nCopy this JSON value as your secret in your configuration file :\n\n")
    print(json.dumps(output_data))
    print()