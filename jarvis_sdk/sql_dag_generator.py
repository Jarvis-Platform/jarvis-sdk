#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""This tool will generate a DAG according to the JSON file passed in.

20190107  : JGU
For now, this tool will generate a workflow containing a sequence of GBQ SQL queries executions.

20190306 : JGU
The "--deploy" switch will work only if this script is executed within the directory where the .sql files are.

ie :
|
|-- someDirectory
|      |
       |-- my_dag_description.json
       |-- sql_001.sql
       |-- step_N.sql
       |-- cleanup.sql

"""

import os
import argparse
import json
import pprint
import base64
import datetime
import warnings
import requests
import pickle
import re
import sys
import tempfile
import copy

from jarvis_sdk import jarvis_config
from jarvis_sdk import jarvis_auth
from jarvis_sdk import jarvis_misc

# Globals
#
_current_version = "2019.07.03.001"

warnings.filterwarnings("ignore", "Your application has authenticated using end user credentials")


def check_task_dependencies_vs_workflow(task_dependencies, workflow):

    # Process workflow
    #
    task_list = []
    for item in workflow:

        task_list.append(item["id"].strip())

    missing_tasks = []
    for line in task_dependencies:

        line = re.sub(">>|<<|\[|\]|,", " ", line)

        for item in line.split():

            if item not in task_list:

                missing_tasks.append(item.strip())

    if len(missing_tasks) > 0:

        print("\n")
        for missing_task in  missing_tasks:
            print("ERROR : the task with ID \"{}\" is present in \"task_dependencies\" but not in \"workflow\". Please fix this.".format(missing_task))

        print("\n")
        return False

    else:

        return True


def check_task_id_naming(workflow):

    # Process workflow
    #
    pattern = "(^[a-zA-Z])([a-zA-Z0-9_]+)([a-zA-Z0-9])$"
    task_list = []
    final_result = True

    for item in workflow:

        result = re.match(pattern, item["id"].strip())

        if not result:
            final_result = False
            print("The task ID \"{}\" is malformed. First character must be a letter, you can use letters, numbers and underscores afterwards, but the last character cannot be an underscore.".format(item["id"].strip()))

    return final_result


def build_header():

    output_payload = """# -*- coding: utf-8 -*-

import datetime
import logging
import sys
import os
import json
import base64
import uuid
import time
import warnings
from jinja2 import Template

from google.cloud import bigquery
from google.cloud import firestore
from google.cloud import storage
from google.cloud import exceptions
from google.oauth2 import service_account
"""

    return output_payload


def build_header_full(dag_name, dag_start_date):

    output_payload = """
import airflow
from airflow.operators.bash_operator import BashOperator
from airflow.operators.python_operator import PythonOperator, ShortCircuitOperator, BranchPythonOperator
from airflow.operators.dummy_operator import DummyOperator
from airflow.models import Variable
from airflow.operators import FashiondDataPubSubPublisherOperator
from airflow.operators import FashiondDataGoogleComputeInstanceOperator

# FD tools
from dependencies import fd_toolbox

default_args = {
    'owner': 'JARVIS',
    'depends_on_past': False,
    'email': [''],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': datetime.timedelta(minutes=2),
    'start_date': datetime.datetime(""" + dag_start_date + """),
    'provide_context': True
}

"""

    # DUmp dag name
    #
    output_payload += "# Globals \n#\n"
    output_payload += "_dag_name = \"" + dag_name + "\"\n"
    output_payload += "_dag_type = \"gbq-to-gbq\"\n"
    output_payload += "_dag_generator_version = \"" + _current_version + "\"\n\r"

    return output_payload


def build_functions(dag_name, environment):

    output_payload = """

def process_bigquery_record(payload, convert_type_to_string=False):

    logging.info("Processing RECORD type ...")

    # Check for field description
    #
    field_description = None
    try:
        field_description = payload['description']
    except Exception:
        field_description = None

    # Check for field MODE
    #
    mode = None
    try:
        mode = payload['mode']
    except Exception:
        mode = "NULLABLE"

    # Check for field FIELDS
    #
    fields = ()
    try:
        fields_list = payload['fields']
        logging.info(payload['fields'])
        list_tuples = []

        for field in fields_list:

            # Field, NAME
            field_name = None
            try:
                field_name = field['name']
            except KeyError:
                # error
                continue

            # Field, TYPE
            field_type = None
            try:
                field_type = field['type'].strip()
            except KeyError:
                # error
                continue

            logging.info("Field name : {} || Field type : {}".format(
                field_name, field_type))

            # Check if field type is RECORD
            #
            if field_type == "RECORD":
                logging.info("Going to process sub Record.")
                processed_record = process_bigquery_record(field)
                logging.info(
                    "Sub Record processed : \\n{}".format(processed_record))
                list_tuples.append(processed_record)

            else:

                # Field, MODE
                field_mode = None
                try:
                    field_mode = field['mode']
                except KeyError:
                    field_mode = "NULLABLE"

                # Field, DESCRIPTION
                field_desc = None
                try:
                    field_desc = field['description']
                except KeyError:
                    field_desc = None

                # Convert FIELD TYPE to STRING
                #
                if convert_type_to_string is True:
                    field_type = "STRING"

                list_tuples.append(bigquery.SchemaField(name=field_name,
                                                        field_type=field_type,
                                                        mode=field_mode,
                                                        description=field_desc))

        fields = tuple(list_tuples)

    except Exception:
        fields = ()

    # Must return a bigquery.SchemaField
    #
    logging.info("Creating SchemaField : name : {} || type : {} || desc. : {} || mode : {} || fields : {}".format(
        payload['name'], payload['type'], field_description, mode, fields))
    return bigquery.SchemaField(payload['name'], payload['type'], description=field_description, mode=mode, fields=fields)

def get_firestore_data(collection, doc_id, item, credentials):

    # Read the configuration is stored in Firestore
    #
    info            = json.loads(credentials)
    credentials     = service_account.Credentials.from_service_account_info(info)
    db              = firestore.Client(credentials=credentials)
    collection      = collection

    return (db.collection(collection).document(doc_id).get()).to_dict()[item]


def set_firestore_data(collection, doc_id, item, value, credentials):

    # Read the configuration is stored in Firestore
    #
    info            = json.loads(credentials)
    credentials     = service_account.Credentials.from_service_account_info(info)
    db              = firestore.Client(credentials=credentials)
    collection      = collection

    date_now = datetime.datetime.now().isoformat('T')
    data = {item : value, "last_updated":date_now}

    db.collection(collection).document(doc_id).set(data, merge=True)


def initialize(**kwargs):

    # Read the configuration is stored in Firestore
    #
    info            = json.loads(Variable.get("COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET"))
    credentials     = service_account.Credentials.from_service_account_info(info)
    db              = firestore.Client(credentials=credentials)
    collection      = "gbq-to-gbq-conf"
    doc_id          = \"""" + dag_name + """\"

    # Delete the Task statuses if it exists
    #
    try:
        db.collection("gbq-to-gbq-tasks-status").document(kwargs["ti"].dag_id + "_" + kwargs["run_id"]).delete()
    except Exception:
        logging.info("No Tasks Statuses found.")

    # Set this task as RUNNING
    #
    task_infos = {}
    task_infos[kwargs["ti"].task_id] = "running"
    db.collection("gbq-to-gbq-tasks-status").document(kwargs["ti"].dag_id + "_" + kwargs["run_id"]).set(task_infos, merge=True)


    data_read = (db.collection(collection).document(doc_id).get()).to_dict()
    data_read['sql'] = {}

    # Push configuration context
    #
    guid = datetime.datetime.today().strftime("%Y%m%d") + "-" + str(uuid.uuid4())
    set_firestore_data('airflow-com', guid, 'configuration_context', data_read, Variable.get("COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET"))
    kwargs['ti'].xcom_push(key='configuration_context', value={})
    kwargs['ti'].xcom_push(key='airflow-com-id', value=guid)
    
    # Push the environment
    kwargs['ti'].xcom_push(key='environment', value=data_read['environment'])
    

    # Push the account
    kwargs['ti'].xcom_push(key='account', value=data_read['account'])

    # Do we need to run this DAG
    # let's check the 'activated' flag
    #
    # 
    dag_activated = True
    try:
        dag_activated = json.loads(data_read["activated"])
    except KeyError:
        print("No activated attribute found in DAGs config. Setting to default : True")

    # Set this task as SUCCESS
    #
    task_infos = {}
    task_infos[kwargs["ti"].task_id] = "success"
    db.collection("gbq-to-gbq-tasks-status").document(kwargs["ti"].dag_id + "_" + kwargs["run_id"]).set(task_infos, merge=True)

    if dag_activated is True:
        return "send_dag_infos_to_pubsub_after_config"
    else:
        return "send_dag_infos_to_pubsub_deactivated"


def log_to_gbq( short_dag_exec_date,
                dag_execution_date,
                dag_run_id,
                dag_name,
                environment,
                source_sql,
                dest_dataset,
                dest_table,
                num_rows_inserted ):

    # Create Bigquery client
    #
    info = json.loads(Variable.get("COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET"))
    credentials = service_account.Credentials.from_service_account_info(info)
    gbq_client = bigquery.Client(credentials=credentials)

    # Dataset
    #
    dataset_ref = gbq_client.dataset("jarvis_plateform_logs")

    # Table
    #
    schema = [
        bigquery.SchemaField('dag_execution_date', 'STRING', mode='NULLABLE'),
        bigquery.SchemaField('dag_run_id', 'STRING', mode='NULLABLE'),
        bigquery.SchemaField('dag_name', 'STRING', mode='NULLABLE'),
        bigquery.SchemaField('environment', 'STRING', mode='NULLABLE'),
        bigquery.SchemaField('source_sql', 'STRING', mode='NULLABLE'),
        bigquery.SchemaField('dest_dataset', 'STRING', mode='NULLABLE'),
        bigquery.SchemaField('dest_table', 'STRING', mode='NULLABLE'),
        bigquery.SchemaField('num_rows_inserted', 'INT64', mode='NULLABLE')
    ]

    # Prepares a reference to the table
    # Create the table if needed
    #
    table_ref = dataset_ref.table("sql_to_gbq_" + short_dag_exec_date)

    try:
        # Check if the table already exists
        #
        gbq_client.get_table(table_ref)

    except Exception as error:

        # The table does not exits, let's create it !
        #
        logging.info("Exception : %s", error)
        gbq_client.create_table(bigquery.Table(table_ref, schema=schema))


    # Prepare the insert query
    #
    query = "INSERT jarvis_plateform_logs.sql_to_gbq_" + short_dag_exec_date + " (dag_execution_date, dag_run_id, dag_name, environment, source_sql, dest_dataset, dest_table, num_rows_inserted) VALUES ('{}','{}','{}','{}','{}','{}','{}',{})"
    query = query.format(   dag_execution_date,
                            dag_run_id,
                            dag_name,
                            environment,
                            source_sql,
                            dest_dataset,
                            dest_table,
                            int(num_rows_inserted) )

    logging.info("QUERY : %s", query)

    job_config = bigquery.QueryJobConfig()

    query_job = gbq_client.query(
        query,
        job_config=job_config
    )

    # Waits for table load to complete.
    #
    query_job.result()

    assert query_job.state == 'DONE'


def execute_gbq(sql_id, env, dag_name, gcp_project_id, bq_dataset, table_name, write_disposition, sql_query_template, run_locally=False, local_sql_query=None, **kwargs):

    # Strip the ENVIRONMENT out of the DAG's name
    # i.e : my_dag_PROD -> my_dag
    #
    stripped_dag_name = dag_name.rpartition("_")[0]

    # Read SQL file according to the configuration specified
    # The configuration is stored in Firestore
    #
    if run_locally is False:
        info            = json.loads(Variable.get("COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET"))
        credentials     = service_account.Credentials.from_service_account_info(info)
        db              = firestore.Client(credentials=credentials)
        collection      = "gbq-to-gbq-conf"
        doc_id          = \"""" + dag_name + """\"

    # Set this task as RUNNING
    #
    if run_locally is False:
        task_infos = {}
        task_infos[kwargs["ti"].task_id] = "running"
        db.collection("gbq-to-gbq-tasks-status").document(kwargs["ti"].dag_id + "_" + kwargs["run_id"]).set(task_infos, merge=True)

        logging.info("Trying to retrieve SQL query from Firestore : %s > %s  : sql -> %s", collection, doc_id, sql_id)

    if run_locally is False:
        data_read = (db.collection(collection).document(doc_id).get()).to_dict()
        data_decoded = base64.b64decode(data_read['sql'][sql_id])
        sql_query = str(data_decoded, 'utf-8')

    else:

        # Local execution
        #
        sql_query = local_sql_query
        logging.info("SQL Query : {}\\n".format(sql_query))

    # Update the configuration context
    #
    # config_context = json.loads(kwargs['ti'].xcom_pull(key='configuration_context'))
    # config_context['sql'][sql_id] = sql_query
    # kwargs['ti'].xcom_push(key='configuration_context', value=json.dumps(config_context))
    #
    if run_locally is False:
        doc_id = kwargs['ti'].xcom_pull(key='airflow-com-id')
        config_context = get_firestore_data('airflow-com', doc_id, 'configuration_context', Variable.get("COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET"))
        config_context['sql'][sql_id] = sql_query
        set_firestore_data('airflow-com', doc_id, 'configuration_context', config_context, Variable.get("COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET"))

    # Replace "sql_query_template" with DAG Execution DATE
    #
    logging.info("sql_query_template : %s", sql_query_template)
    if sql_query_template != "":

        execution_date = kwargs.get('ds')
        logging.info("execution_date : %s", execution_date)

        sql_query = sql_query.replace("{{" + sql_query_template + "}}", execution_date)

        # templated_sql = Template(sql_query)
        # sql_query = templated_sql.render("{}".format(sql_query_template)=execution_date)

    logging.info("SQL Query : \\n\\r%s", sql_query)

    if run_locally is False:
        info                = json.loads(Variable.get("COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET"))
        credentials         = service_account.Credentials.from_service_account_info(info)
        gbq_client          = bigquery.Client(project=gcp_project_id, credentials=credentials)

    else:

        gbq_client          = bigquery.Client(project=gcp_project_id)

    dataset_id          = bq_dataset
    dataset_ref         = gbq_client.dataset(dataset_id)
    dataset             = bigquery.Dataset(dataset_ref)
    dataset.location    = "EU"
    # gbq_client.create_dataset(dataset)

    job_config = bigquery.QueryJobConfig()
    table_ref = gbq_client.dataset(dataset_id).table(table_name)

    # Try to retrieve schema
    # This will be used later on in a case of query with WRITE_TRUNCATE
    try:
        retrieved_schema = list(gbq_client.get_table(table_ref).schema)
        logging.info(retrieved_schema)
    except exceptions.NotFound:
        logging.info("Table {} does not exist, cannot retrieve schema.".format(table_name))
        retrieved_schema = None

    job_config.destination = table_ref
    job_config.write_disposition = write_disposition

    query_job = gbq_client.query(
        sql_query,
        location="EU",
        job_config=job_config
    )

    results = None
    try:
        results = query_job.result()  # Waits for query to complete.

    except exceptions.GoogleCloudError as error:
        logging.error("ERROR while executing query : %s", error)
        raise error

    try:

        # Update schema
        #
        if (write_disposition == "WRITE_TRUNCATE") and (retrieved_schema is not None):
            logging.info("Updating table schema ...")
            table_ref = gbq_client.dataset(dataset_id).table(table_name)
            table_to_modify = gbq_client.get_table(table_ref)
            table_to_modify.schema = retrieved_schema
            table_to_modify = gbq_client.update_table(table_to_modify, ["schema"])
            assert table_to_modify.schema == retrieved_schema

        next(iter(results))
        logging.info("Output of result : %s", results)
        logging.info("Rows             : %s", results.total_rows)

        if run_locally is False:
            log_to_gbq( kwargs["ds_nodash"],
                        kwargs["ds"],
                        kwargs["run_id"],
                        _dag_name,
                        \"""" + environment + """\",
                        sql_id,
                        bq_dataset,
                        table_name,
                        results.total_rows )
    except:
        logging.info("Query returned no result...")

    # Set this task as SUCCESS
    #
    if run_locally is False:
        task_infos = {}
        task_infos[kwargs["ti"].task_id] = "success"
        db.collection("gbq-to-gbq-tasks-status").document(kwargs["ti"].dag_id + "_" + kwargs["run_id"]).set(task_infos, merge=True)



def execute_bq_copy_table(  source_gcp_project_id, 
                            source_bq_dataset, 
                            source_bq_table, 
                            destination_gcp_project_id, 
                            destination_bq_dataset, 
                            destination_bq_table,
                            destination_bq_table_date_suffix,
                            destination_bq_table_date_suffix_format,
                            run_locally=False,
                            **kwargs):


    logging.info("source_gcp_project_id : %s", source_gcp_project_id)
    logging.info("source_bq_dataset : %s", source_bq_dataset)
    logging.info("source_bq_table : %s", source_bq_table)
    logging.info("destination_gcp_project_id : %s", destination_gcp_project_id)
    logging.info("destination_bq_dataset : %s", destination_bq_dataset)
    logging.info("destination_bq_table : %s", destination_bq_table)
    logging.info("destination_bq_table_date_suffix : %s", str(destination_bq_table_date_suffix))
    logging.info("destination_bq_table_date_suffix_format : %s", destination_bq_table_date_suffix_format)

    # Create Bigquery client
    #
    if run_locally is False:
        info = json.loads(Variable.get("COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET"))
        credentials = service_account.Credentials.from_service_account_info(info)
        gbq_client = bigquery.Client(project="fd-jarvis-datalake", credentials=credentials)
        db = firestore.Client(credentials=credentials)

    else:

        gbq_client = bigquery.Client(project="fd-jarvis-datalake")

    # Set this task as RUNNING
    #
    if run_locally is False:
        task_infos = {}
        task_infos[kwargs["ti"].task_id] = "running"
        db.collection("gbq-to-gbq-tasks-status").document(kwargs["ti"].dag_id + "_" + kwargs["run_id"]).set(task_infos, merge=True)

    # Source data
    #
    source_dataset = gbq_client.dataset(source_bq_dataset, project=source_gcp_project_id)
    source_table_ref = source_dataset.table(source_bq_table)

    # Destination
    #
    if destination_bq_table_date_suffix is True:
        today = datetime.datetime.now().strftime(destination_bq_table_date_suffix_format)
        logging.info("Today : %s", today)
        destination_bq_table += "_" + today
        logging.info("Destination table : %s", destination_bq_table)
 
    dest_table_ref = gbq_client.dataset(destination_bq_dataset, project=destination_gcp_project_id).table(destination_bq_table)

    job_config = bigquery.CopyJobConfig()
    job_config.write_disposition = "WRITE_TRUNCATE"

    job = gbq_client.copy_table(
        source_table_ref,
        dest_table_ref,
        location="EU",
        job_config = job_config
    )

    job.result()  # Waits for job to complete.
    assert job.state == "DONE"

    # Set this task as SUCCESS
    #
    if run_locally is False:
        task_infos = {}
        task_infos[kwargs["ti"].task_id] = "success"
        db.collection("gbq-to-gbq-tasks-status").document(kwargs["ti"].dag_id + "_" + kwargs["run_id"]).set(task_infos, merge=True)



def execute_bq_create_table(gcp_project_id,
                            force_delete,
                            bq_dataset, 
                            bq_table,
                            bq_table_description,
                            bq_table_schema,
                            bq_table_clustering_fields,
                            bq_table_timepartitioning_field,
                            bq_table_timepartitioning_expiration_ms,
                            bq_table_timepartitioning_require_partition_filter,
                            run_locally=False,
                            **kwargs):


    logging.info("gcp_project_id : %s", gcp_project_id)
    logging.info("bq_dataset : %s", bq_dataset)
    logging.info("bq_table : %s", bq_table)
    
    # Create Bigquery client
    #
    if run_locally is False:
        info = json.loads(Variable.get("COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET"))
        credentials = service_account.Credentials.from_service_account_info(info)
        gbq_client = bigquery.Client(project=gcp_project_id, credentials=credentials)
        db = firestore.Client(credentials=credentials)
    else:
        gbq_client = bigquery.Client(project=gcp_project_id)

    # Set this task as RUNNING
    #
    if run_locally is False:
        logging.info("Setting task status : running")
        task_infos = {}
        task_infos[kwargs["ti"].task_id] = "running"
        time.sleep(1)
        db.collection("gbq-to-gbq-tasks-status").document(kwargs["ti"].dag_id + "_" + kwargs["run_id"]).set(task_infos, merge=True)

    # Instantiate a table object
    #
    dataset_ref = gbq_client.dataset(bq_dataset, project=gcp_project_id)
    table_ref = dataset_ref.table(bq_table)
    table = bigquery.Table(table_ref)

    # Check wether the table already exist or not
    #
    try:
        table_tmp = gbq_client.get_table(table_ref)
        logging.info("Table {} exists.".format(gcp_project_id + "." + bq_dataset + "." + bq_table))

        if force_delete is True:
            logging.info("Table {} is flagged to be deleted.".format(gcp_project_id + "." + bq_dataset + "." + bq_table))
            gbq_client.delete_table(gcp_project_id + "." + bq_dataset + "." + bq_table)

        else:

            # Is the table partitioned
            #
            time_partitioning = table_tmp.partitioning_type

            # Let's delete the current date partition
            #
            if time_partitioning is not None:
                table_name_with_partition = gcp_project_id + "." + bq_dataset + "." + bq_table + "$" + (kwargs.get('ds')).replace("-", "")
                logging.info("Delete partition : %s", table_name_with_partition)
                gbq_client.delete_table(table_name_with_partition)

            # Set this task as SUCCESS
            #
            logging.info("Setting task status : success")
            task_infos = {}
            task_infos[kwargs["ti"].task_id] = "success"
            time.sleep(1)
            db.collection("gbq-to-gbq-tasks-status").document(kwargs["ti"].dag_id + "_" + kwargs["run_id"]).set(task_infos, merge=True)
            
            return

    except exceptions.NotFound:
        logging.info("Table {} does not exist. Let's create it.".format(gcp_project_id + ":" + bq_dataset + "." + bq_table))

    except ValueError as error:
        logging.info(error)
        logging.info("Table {} exists and is not time partitioned.".format(gcp_project_id + ":" + bq_dataset + "." + bq_table))

        # Set this task as SUCCESS
        #
        if run_locally is False:
            logging.info("Setting task status : success")
            task_infos = {}
            task_infos[kwargs["ti"].task_id] = "success"
            time.sleep(1)
            db.collection("gbq-to-gbq-tasks-status").document(kwargs["ti"].dag_id + "_" + kwargs["run_id"]).set(task_infos, merge=True)

        return


    # Get a new REF
    #
    table = bigquery.Table(table_ref)

    # Set table description
    #
    table.description = bq_table_description

    # Processing the table schema
    #
    table_schema_in = bq_table_schema
    table_schema_out = []

    logging.info("Table Schema :")

    for item in table_schema_in:

        # Field, NAME
        field_name = None
        try:
            field_name = item['name'].strip()
        except KeyError:
            # error
            logging.info("ERROR : field does note have NAME")
            continue
        
        # Field, TYPE
        field_type = None
        try:
            field_type = item['type'].strip()
        except KeyError:
            # error
            logging.info("ERROR : field does note have TYPE")
            continue

        logging.info("Field name : {} || Field type : {}".format(field_name, field_type))

        # Check for field description
        field_description = None
        try:
            field_description = item['description']
        except Exception:
            field_description = None

        # Check for field MODE
        mode = None
        try:
            mode = item['mode']
        except Exception:
            mode = "NULLABLE"

        # Process RECORD type
        #
        if field_type == "RECORD":
            if run_locally is False:
                schemafield_to_add = fd_toolbox.process_bigquery_record(item)
            else:
                schemafield_to_add = process_bigquery_record(item)

            logging.info("Record processed : \\n{}".format(schemafield_to_add))

        else:
            schemafield_to_add = bigquery.SchemaField(field_name, field_type, description=field_description, mode=mode)

        table_schema_out.append(schemafield_to_add)        
        logging.info("SchemaField added : {}".format(schemafield_to_add))

    # Some infos
    #
    logging.info(table_schema_out)
    

    # Processing clustering fields
    #
    if (bq_table_clustering_fields is not None) and (len(bq_table_clustering_fields) > 0):

        table.clustering_fields = bq_table_clustering_fields
        logging.info("Clustering fields : %s", str(bq_table_clustering_fields))

        # Clustering fields option needs time_partition enabled
        #
        table.time_partitioning = bigquery.table.TimePartitioning()

    else:
        logging.info("No clustering fields option to process.")

    # Processing time partitioning options
    #
    if (bq_table_timepartitioning_field is not None) or (bq_table_timepartitioning_expiration_ms is not None) or (bq_table_timepartitioning_require_partition_filter is not None):

        logging.info("Time Partitioning FIELD                    : %s", bq_table_timepartitioning_field)
        logging.info("Time Partitioning EXPIRATION MS            : %s", bq_table_timepartitioning_expiration_ms)
        logging.info("Time Partitioning REQUIRE PARTITION FILTER : %s", bq_table_timepartitioning_require_partition_filter)
        table.time_partitioning = bigquery.table.TimePartitioning(field=bq_table_timepartitioning_field, expiration_ms=bq_table_timepartitioning_expiration_ms)
        table.require_partition_filter = bq_table_timepartitioning_require_partition_filter

    # Schema
    #
    table.schema = table_schema_out

    for item in table.schema:
        logging.info(item)

    # Create table
    #
    job = gbq_client.create_table(table)

    # Set this task as SUCCESS
    #
    if run_locally is False:
        logging.info("Setting task status : success")
        task_infos = {}
        task_infos[kwargs["ti"].task_id] = "success"
        time.sleep(1)
        db.collection("gbq-to-gbq-tasks-status").document(kwargs["ti"].dag_id + "_" + kwargs["run_id"]).set(task_infos, merge=True)

"""

    return output_payload


def build_complementary_code():

    output_payload = """

    # Initial logging
    #
    send_dag_infos_to_pubsub_start = FashiondDataPubSubPublisherOperator(
        task_id="send_dag_infos_to_pubsub_start",
        dag=dag,
        google_credentials="{{ var.value.COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET }}",
        payload={"dag_id": _dag_name,
                 "dag_execution_date": "{{ execution_date }}",
                 "dag_run_id": "{{ run_id }}",
                 "dag_type": _dag_type,
                 "dag_generator_version": _dag_generator_version,
                 "job_id": _dag_type + "|" + _dag_name,
                 "status": "RUNNING"
                 }
    )

    # First step
    #
    initialize = BranchPythonOperator(
        task_id="initialize",
        dag=dag,
        python_callable = initialize
    )

    # Some logging after reading the configuration
    #
    send_dag_infos_to_pubsub_after_config = FashiondDataPubSubPublisherOperator(
        task_id = "send_dag_infos_to_pubsub_after_config",
        dag = dag,
        google_credentials = "{{ var.value.COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET }}",
        payload = { "dag_id" : _dag_name ,
                    "dag_execution_date" : "{{ execution_date }}",
                    "dag_run_id" : "{{ run_id }}",
                    "dag_type": _dag_type,
                    "dag_generator_version": _dag_generator_version,
                    "configuration_context": {"collection" : "airflow-com", "doc_id" : "{{ task_instance.xcom_pull(key='airflow-com-id') }}", "item" : "configuration_context"},
                    "account": "{{task_instance.xcom_pull(key='account')}}",
                    "environment": "{{task_instance.xcom_pull(key='environment')}}",
                    "job_id": _dag_type + "|" + _dag_name,
                    "status": "RUNNING"
                }
    )

    # In case of failure
    #
    send_dag_infos_to_pubsub_failed = FashiondDataPubSubPublisherOperator(
        task_id = "send_dag_infos_to_pubsub_failed",
        dag = dag,
        trigger_rule='one_failed',
        google_credentials = "{{ var.value.COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET }}",
        payload = { "dag_id" : _dag_name ,
                    "dag_execution_date" : "{{ execution_date }}",
                    "dag_run_id" : "{{ run_id }}",
                    "dag_type": _dag_type,
                    "dag_generator_version": _dag_generator_version,
                    "job_id": _dag_type + "|" + _dag_name,
                    "status": "FAILED"
                }
    )

    # Final step
    #
    send_dag_infos_to_pubsub = FashiondDataPubSubPublisherOperator(
        task_id = "send_dag_infos_to_pubsub",
        dag = dag,
        google_credentials = "{{ var.value.COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET }}",
        payload = { "dag_id" : _dag_name ,
                    "dag_execution_date" : "{{ execution_date }}",
                    "dag_run_id" : "{{ run_id }}",
                    "dag_type": _dag_type,
                    "dag_generator_version": _dag_generator_version,
                    "configuration_context": {"collection" : "airflow-com", "doc_id" : "{{ task_instance.xcom_pull(key='airflow-com-id') }}", "item" : "configuration_context"},
                    "account": "{{task_instance.xcom_pull(key='account')}}",
                    "environment": "{{task_instance.xcom_pull(key='environment')}}",
                    "job_id": _dag_type + "|" + _dag_name,
                    "status": "SUCCESS"
                }
    )

    # Send status via PubSub in case the "activated" configuration flag is set to FALSE
    #
    send_dag_infos_to_pubsub_deactivated = FashiondDataPubSubPublisherOperator(
        task_id = "send_dag_infos_to_pubsub_deactivated",
        dag = dag,
        google_credentials = "{{ var.value.COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET }}",
        payload = { "dag_id" : _dag_name ,
                    "dag_execution_date" : "{{ execution_date }}",
                    "dag_run_id" : "{{ run_id }}",
                    "dag_type": _dag_type,
                    "dag_generator_version": _dag_generator_version,
                    "configuration_context": {"collection" : "airflow-com", "doc_id" : "{{ task_instance.xcom_pull(key='airflow-com-id') }}", "item" : "configuration_context"},
                    "account": "{{task_instance.xcom_pull(key='account')}}",
                    "environment": "{{task_instance.xcom_pull(key='environment')}}",
                    "job_id": _dag_type + "|" + _dag_name,
                    "status": "SUCCESS"
                }
    )

"""

    return output_payload


def build_sql_task(payload, env, default_gcp_project_id, default_bq_dataset, default_write_disposition, global_path, run_locally=False, task_id=None):

    # Check for overridden values : GCP Project ID, Dataset, ...
    #
    gcp_project_id = None
    bq_dataset = None
    write_disposition = None

    try:
        gcp_project_id = payload["gcp_project_id"]

    except KeyError:
        gcp_project_id = default_gcp_project_id

    try:
        bq_dataset = payload["bq_dataset"]

    except KeyError:
        bq_dataset = default_bq_dataset

    try:
        write_disposition = payload["write_disposition"]

    except KeyError:
        write_disposition = default_write_disposition

    # Retrieve sql_query_template
    #
    temporary_tablesql_query_template = ""
    try:
        sql_query_template = payload["sql_query_template"]
    except KeyError:
        sql_query_template = ""

    # Retrieve documentation
    #
    dag_doc = ""
    try:
        with open("./" + payload["doc_md"], 'r') as file:
            dag_doc = file.read()
    except:
        print("No documentation provided for task : ", payload["id"])

    # Retrieve SQL file to inject into Documentation
    #
    sql_doc = ""
    with open("./" + payload["sql_file"], 'r') as file:
        sql_doc += file.read().replace("\n", "\n\n")

    if run_locally is True:

        output_payload = """def """ + task_id + """():

    logging.info("\\n\\nExecuting task with id : {}\\n".format(\"""" + task_id + """\"))

    execute_gbq(sql_id = \"""" + payload["id"] + """\",
        env = \"""" + env + """\",
        dag_name = "TEST",
        gcp_project_id = \"""" + gcp_project_id + """\",
        bq_dataset = \"""" + bq_dataset + """\",
        table_name = \"""" + payload["table_name"] + """\",
        write_disposition = \"""" + write_disposition + """\",
        sql_query_template = \"""" + sql_query_template + """\",
        run_locally = True,
        local_sql_query = \"\"\"""" + sql_doc + """\"\"\"
        )

"""

    else:

        sql_doc = sql_doc.replace("`", "'")

        output_payload = ""
        output_payload += "    " + payload["id"] + " = "
        output_payload += """PythonOperator(
                task_id = \"""" + payload["id"] + """\",
                dag = dag,
                python_callable = execute_gbq,
                op_kwargs={ "sql_id" : \"""" + payload["id"] + """\",
                            "env" : \"""" + env + """\",
                            "dag_name" : _dag_name,
                            "gcp_project_id" : \"""" + gcp_project_id + """\",
                            "bq_dataset" : \"""" + bq_dataset + """\",
                            "table_name" : \"""" + payload["table_name"] + """\",
                            "write_disposition" : \"""" + write_disposition + """\",
                            "sql_query_template" : \"""" + sql_query_template + """\"
                            }
                )

    """ + payload["id"] + """.doc_md = \"\"\"""" + dag_doc + """

    # **SQL Query**

    """ + sql_doc + """
    \"\"\"

    """

    return output_payload


def build_copy_bq_table_task(payload, default_gcp_project_id, default_bq_dataset, run_locally=False, task_id=None):

    # Check for overridden values : GCP Project ID, Dataset, ...
    #
    gcp_project_id = None
    bq_dataset = None

    try:
        gcp_project_id = payload["gcp_project_id"]

    except KeyError:
        gcp_project_id = default_gcp_project_id

    try:
        bq_dataset = payload["bq_dataset"]

    except KeyError:
        bq_dataset = default_bq_dataset

    destination_bq_table_date_suffix = "False"
    destination_bq_table_date_suffix_format = ""
    try:
        destination_bq_table_date_suffix = str(payload["destination_bq_table_date_suffix"])
        destination_bq_table_date_suffix_format = payload["destination_bq_table_date_suffix_format"].strip()
    except KeyError:
        print()

    # Prepare output value
    output_payload = ""

    if run_locally is True:

        output_payload += """def """ + task_id + """():

    logging.info("\\n\\nExecuting task with id : {}\\n".format(\"""" + task_id + """\"))

    execute_bq_copy_table(source_gcp_project_id = \"""" + payload["source_gcp_project_id"].strip() + """\",
        source_bq_dataset = \"""" + payload["source_bq_dataset"].strip() + """\",
        source_bq_table = \"""" + payload["source_bq_table"].strip() + """\",
        destination_gcp_project_id = \"""" + gcp_project_id.strip() + """\",
        destination_bq_dataset = \"""" + bq_dataset.strip() + """\",
        destination_bq_table = \"""" + payload["destination_bq_table"].strip() + """\",
        destination_bq_table_date_suffix = """ + destination_bq_table_date_suffix + """,
        destination_bq_table_date_suffix_format = \"""" + destination_bq_table_date_suffix_format + """\",
        run_locally = True
        )

"""

    else:

        output_payload += "    " + payload["id"] + " = "
        output_payload += """PythonOperator(
            task_id=\"""" + payload["id"] + """\",
            dag=dag,
            python_callable=execute_bq_copy_table,
            op_kwargs={
                "source_gcp_project_id" : \"""" + payload["source_gcp_project_id"].strip() + """\",
                "source_bq_dataset" : \"""" + payload["source_bq_dataset"].strip() + """\",
                "source_bq_table" : \"""" + payload["source_bq_table"].strip() + """\",
                "destination_gcp_project_id" : \"""" + gcp_project_id.strip() + """\",
                "destination_bq_dataset" : \"""" + bq_dataset.strip() + """\",
                "destination_bq_table" : \"""" + payload["destination_bq_table"].strip() + """\",
                "destination_bq_table_date_suffix" : """ + destination_bq_table_date_suffix + """,
                "destination_bq_table_date_suffix_format" : \"""" + destination_bq_table_date_suffix_format + """\"
            }
        )
"""

    return output_payload


def build_create_bq_table_task(payload, default_gcp_project_id, default_bq_dataset, global_path, run_locally=False, task_id=None):

    # Prepare output value
    output_payload = ""

    # Check for overridden values : GCP Project ID, Dataset, ...
    #
    gcp_project_id = None
    bq_dataset = None

    try:
        gcp_project_id = payload["gcp_project_id"]

    except KeyError:
        gcp_project_id = default_gcp_project_id

    try:
        bq_dataset = payload["bq_dataset"]

    except KeyError:
        bq_dataset = default_bq_dataset

    # Open DDL file
    #
    # Add the parameters inside the current payload to save them down the process.
    #
    with open(payload["ddl_file"], "r") as f:
        try:
            payload_ddl = json.load(f)
        except Exception as ex:
            print("\nError while parsing DDL JSON file : {}".format(f.name))
            print(ex)
            return False

        payload["bq_table_description"] = payload_ddl["bq_table_description"]
        payload["bq_table_schema"] = payload_ddl["bq_table_schema"]

        # Optional fields
        #
        try:
            payload["bq_table_clustering_fields"] = payload_ddl["bq_table_clustering_fields"]
        except KeyError:
            print("Optional \"bq_table_clustering_fields\" parameter not provided.")

        try:
            payload["bq_table_timepartitioning_field"] = payload_ddl["bq_table_timepartitioning_field"]
        except KeyError:
            print("Optional \"bq_table_timepartitioning_field\" parameter not provided.")

        try:
            payload["bq_table_timepartitioning_expiration_ms"] = payload_ddl["bq_table_timepartitioning_expiration_ms"]
        except KeyError:
            print("Optional \"bq_table_timepartitioning_expiration_ms\" parameter not provided.")

        try:
            payload["bq_table_timepartitioning_require_partition_filter"] = payload_ddl["bq_table_timepartitioning_require_partition_filter"]
        except KeyError:
            print("Optional \"bq_table_timepartitioning_require_partition_filter\" parameter not provided.")

    # Table description
    #
    table_description = ""
    try:
        table_description = payload["bq_table_description"].strip()
    except KeyError:
        table_description = ""

    # Table Schema
    #
    table_schema = []
    try:
        table_schema = payload["bq_table_schema"]
    except KeyError:
        table_schema = []

    # Retrieve clustering fields options
    # Optional
    #
    bq_table_clustering_fields = None
    try:
        bq_table_clustering_fields = payload['bq_table_clustering_fields']
    except KeyError:
        bq_table_clustering_fields = None

    # Retrieve "force_delete" flag
    #
    force_delete = False
    try:
        force_delete = payload['force_delete']
    except KeyError:
        force_delete = False

    # Retrieve BQ Table Time Partitioning options
    # These are optional
    #
    bq_table_timepartitioning_field = None
    bq_table_timepartitioning_expiration_ms = None
    bq_table_timepartitioning_require_partition_filter = None
    try:
        bq_table_timepartitioning_field = payload['bq_table_timepartitioning_field']
    except KeyError:
        bq_table_timepartitioning_field = None
    try:
        bq_table_timepartitioning_expiration_ms = payload['bq_table_timepartitioning_expiration_ms']
    except KeyError:
        bq_table_timepartitioning_expiration_ms = None
    try:
        bq_table_timepartitioning_require_partition_filter = payload[
            'bq_table_timepartitioning_require_partition_filter']
    except KeyError:
        bq_table_timepartitioning_require_partition_filter = None


    if run_locally is True:

        output_payload += """def """ + task_id + """():

    logging.info("\\n\\nExecuting task with id : {}\\n".format(\"""" + task_id + """\"))

    execute_bq_create_table(gcp_project_id = \"""" + gcp_project_id + """\",
        force_delete = """ + str(force_delete) + """,
        bq_dataset = \"""" + bq_dataset + """\",
        bq_table = \"""" + payload["bq_table"].strip() + """\",
        bq_table_description = \"""" + table_description + """\",
        bq_table_schema = """ + str(table_schema) + """,
        bq_table_clustering_fields = """ + str(bq_table_clustering_fields) + """,
        bq_table_timepartitioning_field = """ + (str(bq_table_timepartitioning_field) if (bq_table_timepartitioning_field is None) else ("\"" + bq_table_timepartitioning_field + "\"")) + """,
        bq_table_timepartitioning_expiration_ms = """ + (str(bq_table_timepartitioning_expiration_ms) if (bq_table_timepartitioning_expiration_ms is None) else ("\"" + bq_table_timepartitioning_expiration_ms + "\"")) + """,
        bq_table_timepartitioning_require_partition_filter = """ + (str(bq_table_timepartitioning_require_partition_filter) if (bq_table_timepartitioning_require_partition_filter is None) else ("\"" + bq_table_timepartitioning_require_partition_filter + "\"")) + """,
        run_locally = True
        )
"""

        return output_payload

    else:

        output_payload += "    " + payload["id"] + " = "
        output_payload += """PythonOperator(
        task_id=\"""" + payload["id"] + """\",
        dag=dag,
        python_callable=execute_bq_create_table,
        op_kwargs={
            "gcp_project_id" : \"""" + gcp_project_id + """\",
            "force_delete" : """ + str(force_delete) + """,
            "bq_dataset" : \"""" + bq_dataset + """\",
            "bq_table" : \"""" + payload["bq_table"].strip() + """\",
            "bq_table_description" : \"""" + table_description + """\",
            "bq_table_schema" : """ + str(table_schema) + """,
            "bq_table_clustering_fields" : """ + str(bq_table_clustering_fields) + """,
            "bq_table_timepartitioning_field" : """ + (str(bq_table_timepartitioning_field) if (bq_table_timepartitioning_field is None) else ("\"" + bq_table_timepartitioning_field + "\"")) + """,
            "bq_table_timepartitioning_expiration_ms" :""" + (str(bq_table_timepartitioning_expiration_ms) if (bq_table_timepartitioning_expiration_ms is None) else ("\"" + bq_table_timepartitioning_expiration_ms + "\"")) + """,
            "bq_table_timepartitioning_require_partition_filter" :""" + (str(bq_table_timepartitioning_require_partition_filter) if (bq_table_timepartitioning_require_partition_filter is None) else ("\"" + bq_table_timepartitioning_require_partition_filter + "\"")) + """
        }
    )
"""

    return output_payload


def build_vm_launcher_task(payload, gcp_project_id, run_locally=False, task_id=None):

    # Infos
    #
    print("Generating VM LAUNCHER task ...")

    if run_locally is True:
        return ""

    # Retrieve parameters
    #
    try:
        vm_delete = payload["vm_delete"]
    except KeyError:
        vm_delete = False

    try:
        vm_working_directory = payload["vm_working_directory"]
    except KeyError:
        vm_working_directory = "/tmp"

    try:
        vm_compute_zone = payload["vm_compute_zone"]
    except KeyError:
        vm_compute_zone = "europe-west1-b"

    try:
        vm_core_number = payload["vm_core_number"]
    except KeyError:
        vm_core_number = "1"

    try:
        vm_memory_amount = payload["vm_memory_amount"]
    except KeyError:
        vm_memory_amount = "4"

    try:
        vm_disk_size = payload["vm_disk_size"]
    except KeyError:
        vm_disk_size = "10"

    # Prepare output value
    #
    output_payload = ""
    output_payload += "    " + payload["id"] + " = "
    output_payload += """FashiondDataGoogleComputeInstanceOperator(
        task_id=\"""" + payload["id"] + """\",
        dag=dag,
        gcp_project_id = \"""" + gcp_project_id + """\",
        script_to_execute =  """ + "{}".format(payload["script_to_execute"])  + """,
        vm_delete = """ + "{}".format(vm_delete)  + """,
        vm_working_directory = """ + "\"{}\"".format(vm_working_directory)  + """,
        vm_compute_zone = """ + "\"{}\"".format(vm_compute_zone)  + """,
        vm_core_number = """ + "\"{}\"".format(vm_core_number)  + """,
        vm_memory_amount = """ + "\"{}\"".format(vm_memory_amount)  + """,
        vm_disk_size = """ + "\"{}\"".format(vm_disk_size)  + """,
        private_key_id = \"COMPOSER_RSA_PRIVATE_KEY_SECRET\"    
    )
"""

    return output_payload


def build_python_script(configuration_file, arguments=None, run_locally=False):

    # Do we run locally ?
    # We need to check the arguments
    #
    local_tasks = []
    if (run_locally is True) and (arguments is not None):

        index = 2
        while index < len(arguments):
            local_tasks.append(arguments[index].strip())
            index += 1

    # Infos
    #
    print("Generating and deploying DAG ...")

    print("File to process      : {}".format(configuration_file))
    environment = "PROD"

    # Open JSON configuration file
    #
    try:
        json_file = open(configuration_file, "r")
        json_payload = json.load(json_file)
        json_file.close()
    except Exception as ex:
        print("Error while parsing JSON file : {}".format(configuration_file))
        print(ex)
        return False

    # Get path of filename
    #
    global_path = jarvis_misc.get_path_from_file(configuration_file)

    # Process environment
    #
    # The value set in the JSON file will always be the greatest priority
    #
    try:
        
        environment = json_payload["environment"].strip()

    except KeyError as ex:

        environment = environment.strip()
    
    print("Environment          : {}".format(environment))

    # Extract dag name and add the ENV
    #
    dag_name = json_payload["configuration_id"] + "_" + environment

    # Extract "start_date" and "schedule_interval"
    #
    dag_start_date = json_payload["start_date"]

    # Extract DAG's description
    #
    dag_description = ""
    try:
        dag_description = json_payload["short_description"]
    except KeyError:
        print("No description provided for the DAG.")
        raise Exception("No description provided for the DAG.")

    # Extract DAG's documentation
    #
    dag_doc = ""
    try:
        dag_documentation = global_path + json_payload["doc_md"]
        with open(dag_documentation, 'r') as file:
            dag_doc = file.read()
    except KeyError:
        print("No Markdown documentation provided for the DAG.")

    # Extract max_active_runs
    #
    max_active_runs = None
    try:
        max_active_runs = json_payload["max_active_runs"]
    except KeyError:
        max_active_runs = 1

    # Extract task_concurrency
    #
    task_concurrency = None
    try:
        task_concurrency = json_payload["task_concurrency"]
    except KeyError:
        task_concurrency = 5

    # Extract catchup
    #
    catchup = False
    try:
        catchup = json_payload["catchup"]
    except KeyError:
        print("Global parameter \"catchup\" not found. Setting to default : False")


    # Extract various default values
    #
    default_gcp_project_id = json_payload["default_gcp_project_id"]
    default_bq_dataset = json_payload["default_bq_dataset"]
    default_write_disposition = json_payload["default_write_disposition"]

    # Extract task dependencies, this should use the Airflow syntax : t1>>t2>>[t31,t32]>>t4
    #
    dag_task_dependencies = json_payload["task_dependencies"]

    # Check that all task declared in "task_dependencies" are properly described in "workflow".
    #
    if check_task_dependencies_vs_workflow(task_dependencies=dag_task_dependencies, workflow=json_payload["workflow"]) is False:
        return False

    # Check that all task IDs are formed properly
    #
    if check_task_id_naming(workflow=json_payload["workflow"]) is False:
        return False

    # Start building the payload
    # build the header
    #
    output_payload = build_header()
    if run_locally is False:
        output_payload += build_header_full(dag_name, dag_start_date)

    # Add the different functions needed
    #
    # if run_locally is False:
    output_payload += build_functions(dag_name, environment)

    # Main code
    #

    # Check for Schedule Interval
    #
    if json_payload["schedule_interval"] == "None":
        dag_schedule_interval = "None"
    else:
        dag_schedule_interval = "\"" + json_payload["schedule_interval"] + "\""

    if run_locally is False:
        output_payload += """
with airflow.DAG(
    _dag_name,
    default_args=default_args,
    concurrency=""" + str(task_concurrency) + """,
    max_active_runs=""" + str(max_active_runs) + """,
    schedule_interval = """ + dag_schedule_interval + """,
    catchup = """ + str(catchup) + """,
    description = \"""" + dag_description + """\") as dag:"""

        output_payload += """
    dag.doc_md = \"\"\"""" + dag_doc + """\"\"\"

    # Create all the task that will execute SQL queries
    #
"""

    # In the case we run locally and the user asked for specific tasks,
    # we need to filter out which task to process
    #
    # First, we make a copy of the original tasks
    #
    tasks_to_process = copy.deepcopy(json_payload["workflow"])

    if (run_locally is True) and (len(local_tasks) > 0):

        tmp_tasks_to_process = []

        for task_requested in local_tasks:
            
            print("Looking for task : {}".format(task_requested))

            found = False

            for item in tasks_to_process:

                if item["id"].strip() == task_requested:

                    tmp_tasks_to_process.append(copy.deepcopy(item))
                    found = True
                    break

            # No match found
            #
            if found is False:
                print("\nThe task \"{}\" that you've requested does not exist in the configuration workflow. Please check and retry.\n".format(task_requested))
                return

        # Finally overwrite the tasks to process
        #
        tasks_to_process = copy.deepcopy(tmp_tasks_to_process)

    # Process all the tasks
    #
    for item in json_payload["workflow"]:
    #
    #for item in tasks_to_process:

        generated_code = ""

        # Retrieve the task type
        #
        task_type = None
        try:
            task_type = item['task_type'].strip()
        except Exception:
            print("Could not retrieve task type for task id : " +
                  item['id'] + ". This task will be considered as SQL query task.")

        if task_type == "copy_gbq_table":
            generated_code = build_copy_bq_table_task(
                item, default_gcp_project_id, default_bq_dataset, run_locally=run_locally, task_id=item['id'])

        elif task_type == "create_gbq_table":
            generated_code = build_create_bq_table_task(
                item, default_gcp_project_id, default_bq_dataset, global_path, run_locally=run_locally, task_id=item['id'])

            if generated_code is False:
                return False

        elif task_type == "vm_launcher":
            generated_code = build_vm_launcher_task(item, default_gcp_project_id, run_locally=run_locally, task_id=item['id'])

        else:
            generated_code = build_sql_task(
                item, environment, default_gcp_project_id, default_bq_dataset, default_write_disposition, global_path, run_locally=run_locally, task_id=item['id'])

        # # Add the result to the main payload
        # #
        # if run_locally is True:
            
        #     output_payload += """    logging.info("\\n\\nExecuting task with id : {}\\n".format(\"""" + item["id"] + """\"))\n\n"""

        output_payload += generated_code + "\n"


    # Add "main" for local execution
    #
    if run_locally is True:

        output_payload += """if __name__ == \"__main__\":

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    root.addHandler(handler)

    warnings.filterwarnings("ignore", "Your application has authenticated using end user credentials")
    
"""

    # Local execution
    # Add "tasks to process" only to the "main"
    #
    if run_locally is True:

        for task in tasks_to_process:

            output_payload += """    """ + task["id"] + """()\n"""


    # Add "initialize" function
    # Add PubSub logging
    #
    if run_locally is False:
        output_payload += build_complementary_code()

    # Add task dependencies
    #
    if run_locally is False:
        output_payload += """
    # Task dependencies
    #
    send_dag_infos_to_pubsub_start >> initialize >> send_dag_infos_to_pubsub_after_config
    initialize >> send_dag_infos_to_pubsub_deactivated
"""
    if run_locally is False:
        if len(dag_task_dependencies) > 0:
            for index in range(0, len(dag_task_dependencies)):
                output_payload += "    " + dag_task_dependencies[index] + "\n"

    # Add the task "send_dag_infos_to_pubsub" as the last task
    #
    if run_locally is False:
        for item in json_payload["workflow"]:
            output_payload += """    """ + \
                item["id"] + """ << send_dag_infos_to_pubsub_after_config\n\r"""
            output_payload += """    """ + \
                item["id"] + """ >> send_dag_infos_to_pubsub\n\r"""
            output_payload += """    """ + \
                item["id"] + """ >> send_dag_infos_to_pubsub_failed\n\r"""

    return output_payload, json_payload, dag_name, environment


def process(configuration_file, run_locally=False, arguments=None, jarvis_sdk_version=None):

    # Force local generation
    #
    output_payload, json_payload, dag_name, environment = build_python_script(configuration_file, arguments=None, run_locally=True)
    with open("test_forced.py", "w") as outfile:
        outfile.write(output_payload)

    # Generate python script
    #
    output_payload, json_payload, dag_name, environment = build_python_script(configuration_file, arguments=arguments, run_locally=run_locally)

    # collection = "gbq-to-gbq-conf"
    # doc_id = dag_name

    data = {}
    sql_data = {}
    short_description_data = {}
    doc_md_data = {}

    index = 0
    for item in json_payload["workflow"]:

        # Info
        print("Processing task : " + item["id"])

        # Retrieve the task type
        #
        task_type = None
        try:
            task_type = item['task_type'].strip()
        except Exception:
            print("Could not retrieve task type for task id : " +
                    item['id'] + ". This task will be considered as SQL query task.")

        # retrieve short description
        #
        short_description = ""
        try:
            short_description = item['short_description'].strip()
            short_description_data[item["id"]] = short_description
        except KeyError:
            print("No short description found. Continue ...")

        # retrieve Markdown documentation
        #
        try:
            with open("./" + item["doc_md"], 'r') as file:
                doc_md = file.read()
                doc_md_data[item["id"]] = doc_md

                # Overwrite in the source configuration
                # )
                json_payload["workflow"][index]['doc_md'] = doc_md

        except KeyError:
            print("No Markdown documentation to process. Continue.")
        except Exception as error:
            print(
                "Error while attempting to read Markdown doc : {}. Check your MD file. Continue.".format(error))

        # Specific processing depending of the task type
        #
        if task_type == "copy_gbq_table":
            print("")
        elif task_type == "create_gbq_table":
            print("")
        elif task_type == "vm_launcher":
            print("")
        else:

            # SQL query
            #
            with open("./" + item["sql_file"], 'r') as file:
                temp = file.read()
                sql_data[item["id"]] = base64.b64encode(
                    bytes(temp, 'utf-8'))

            # Retrieve temporary_table flag
            #
            try:
                temporary_table = item["temporary_table"]
                # Everything is fine

            except KeyError:

                # We set the flag to False and save it back to the main payload
                #
                json_payload["workflow"][index]['temporary_table'] = False


        index += 1
    # END FOR

    # Add SQL data
    data["sql"] = sql_data

    # Add short descriptions
    data['short_descriptions'] = short_description_data

    # Add Markdown documentations
    data['docs_md'] = doc_md_data

    # Add account
    data['account'] = json_payload['account']

    # Add environment
    data['environment'] = environment

    # Let's add the whole configuration file as well
    #
    data["configuration"] = json_payload

    # Add info for regular processing by the API
    #
    data["configuration_type"] = "gbq-to-gbq"
    data["configuration_id"] = dag_name
    data["client_type"] = "jarvis-sdk"
    data["client_version"] = jarvis_sdk_version

    # Process the "run locally" option
    #
    if run_locally is True:

        # Run locally
        #
        with tempfile.TemporaryDirectory() as tmpdirname:

            print(tmpdirname)

            tmp_file_path = tmpdirname + "test.py"

            # Paste the file
            #
            with open("test.py", "w") as outfile:
               outfile.write(output_payload)

            with open(tmp_file_path, "w") as outfile:
            
                outfile.write(output_payload)

                print("\n\nThe TTT configuration will now run locally...\n\n")

                # Python executable used here
                #
                python_executable = sys.executable
                print("Python executable used : {}\n".format(python_executable))

                # Execute the file
                #
                os.system(python_executable + " " + tmp_file_path + " 1")

        return

    #######################
    # Prepare call to API #
    #######################

    # Get configuration
    #
    print()
    print("Get JARVIS configuration ...")
    jarvis_configuration = jarvis_config.get_jarvis_configuration_file()

    # Get firebase user
    #
    print("Get user information ...")
    firebase_user = jarvis_auth.get_refreshed_firebase_user(jarvis_configuration)

    # Get list of project profiles open to the user and ask him to pick one
    #
    ret_code, project_profile = jarvis_misc.choose_project_profiles(jarvis_configuration, firebase_user)
    if ret_code is False:
        return False

    # Check if a DAG with the same name is already deployed
    #
    try:

        print("Calling JARVIS API ...")

        url = jarvis_configuration["jarvis_api_endpoint"] + "dag-generator-v2"
        payload = {
            "payload": {
                "resource": "check_dag_exists",
                "dag_file" : {
                    "name": dag_name + ".py"
                },
                "project_profile": project_profile
            }
        }
        headers = {
            "Content-type": "application/json",
            "Authorization": "Bearer " + firebase_user["idToken"]}

        r = requests.put(url, headers=headers, data=json.dumps(payload), verify=jarvis_configuration["perform_ssl_verification"])

        if r.status_code == 200:
            response = r.json()
            print(response["payload"]["message"])

            # DAG file already exists
            # We need to ask the user if everything is OK
            #
            while True:
                print("The DAG {} already exists, do you want to overwrite it y/n ? : ".format(dag_name), end='', flush=True)
                user_value = input()

                if user_value == "y":
                    break
                elif user_value == "n":
                    return True
                else:
                    continue

        elif r.status_code == 404:
            # Everything is OK
            print(str(r.content, "utf-8"))
        else:
            print("\nError : %s\n" % str(r.content, "utf-8"))
            print(r.json())
            return False

    except Exception as ex:
        print("Error while trying to contact Jarvis API ...")
        print(ex)
        return False


    # Process data
    #
    pickled_data = pickle.dumps(data)
    encoded = base64.b64encode(pickled_data) 
    encoded = str(encoded, "utf-8")

    # Process payload
    #
    pickled_payload = pickle.dumps(output_payload)
    encoded_payload = base64.b64encode(pickled_payload)
    encoded_payload = str(encoded_payload, "utf-8")

    # Call API
    #
    try:

        print("Calling JARVIS API ...")

        url = jarvis_configuration["jarvis_api_endpoint"] + "dag-generator-v2"
        payload = {
            "payload": {
                "resource": encoded,
                "dag_file" : {
                    "name" : dag_name + ".py",
                    "data" : encoded_payload
                },
                "project_profile": project_profile,
                "uid" : firebase_user["userId"],
            }
        }
        headers = {
            "Content-type": "application/json",
            "Authorization": "Bearer " + firebase_user["idToken"]}

        r = requests.put(url, headers=headers, data=json.dumps(payload), verify=jarvis_configuration["perform_ssl_verification"])

        if r.status_code != 200:
            print("\nError : %s\n" % str(r.content, "utf-8"))
            print(r.json())
            return False
        else:
            response = r.json()
            print(response["payload"]["message"])
            return True

    except Exception as ex:
        print("Error while trying to contact Jarvis API ...")
        print(ex)
        return False
