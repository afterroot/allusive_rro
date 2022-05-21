#!/bin/bash

gpg --passphrase=${ENCRYPT_KEY} --cipher-algo AES256 --symmetric --output release/keystore.gpg release/keystore.jks
