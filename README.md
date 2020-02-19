# Jarvis SDK by Fashiondata.io

## Changelog

### Release 1.1.0 : 2020-02-19

* Added TTT DAG file checking upon deployment. The user must validate if he wants to overwrite TTT DAG.
* Removed Project selection validation.

### Release 1.0.1 : 2020-02-10

* Fixed seek() error on file read

### Release 0.0.16 : 2020-01-10

* Removed ASCII art
* Storage-to-tables : check for JSON syntax for DDL files as well

### Release 0.0.15 : 2019-xx-xx

* Table-To-Table : GBQ table schema will be preserved upon WRITE_TRUNCATE
* Minor fixes


### Release 0.0.14 : 2019-11-26

* Table-To-Table : added nested RECORD fields support for Bigquery table creation.


### Release 0.0.13 : 2019-11-15

* Storage-To-Tables : "jarvis create configuration" support


### Release 0.0.12 : 2019-11-04

* Added Storage-To-Tables configuration support.
* Table To Table (gbq to gbq) : "create_gbq_table" tasks will now use an external DDL file to describe the table schema.


### Release 0.0.11 : 2019-10-23

* Table To Table (gbq to gbq) configuration will now use "configuration_type" and "configuration_id".
* Table To Table (gbq to gbq) configuration DOES NOT need "dag_name" parameter anymore.
* Storage To Storage configuration accepts "gcp_project_id" in the "source" section if the "source_type" is "gcs".


### Release 0.0.10 : 2019-09-20

* Added auto creation of ".bash_profile" for Max OS X
* Added password double check upon user creation
* Added SQL file path management for "table-to-storage" deploy command
* Added : jarvis create configuration CONFIGURATION_TYPE command
* Added : jarvis check configuration CONFIG.json command
* Added : project profiles management

