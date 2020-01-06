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

from jarvis_sdk import jarvis_config
from jarvis_sdk import jarvis_auth
from jarvis_sdk import jarvis_misc

# Globals
#
_current_version = "2019.07.03.001"

warnings.filterwarnings("ignore", "Your application has authenticated using end user credentials")


def build_header(dag_name, dag_start_date):

    output_payload = """# -*- coding: utf-8 -*-

import datetime
import logging
import os
import json
import base64
import uuid

import airflow
from airflow.operators.bash_operator import BashOperator
from airflow.operators.python_operator import PythonOperator, ShortCircuitOperator, BranchPythonOperator
from airflow.operators.dummy_operator import DummyOperator
from airflow.models import Variable
from airflow.operators import FashiondDataPubSubPublisherOperator
from airflow.operators import FashiondDataGoogleComputeInstanceOperator
from jinja2 import Template

from google.cloud import bigquery
from google.cloud import firestore
from google.cloud import storage
from google.cloud import exceptions
from google.oauth2 import service_account

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


def execute_gbq(sql_id, env, dag_name, gcp_project_id, bq_dataset, table_name, write_disposition, sql_query_template, **kwargs):

    # Strip the ENVIRONMENT out of the DAG's name
    # i.e : my_dag_PROD -> my_dag
    #
    stripped_dag_name = dag_name.rpartition("_")[0]

    # Read SQL file according to the configuration specified
    # The configuration is stored in Firestore
    #
    info            = json.loads(Variable.get("COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET"))
    credentials     = service_account.Credentials.from_service_account_info(info)
    db              = firestore.Client(credentials=credentials)
    collection      = "gbq-to-gbq-conf"
    doc_id          = \"""" + dag_name + """\"

    logging.info("Trying to retrieve SQL query from Firestore : %s > %s  : sql -> %s", collection, doc_id, sql_id)

    data_read = (db.collection(collection).document(doc_id).get()).to_dict()
    data_decoded = base64.b64decode(data_read['sql'][sql_id])
    sql_query = str(data_decoded, 'utf-8')

    # Update the configuration context
    #
    # config_context = json.loads(kwargs['ti'].xcom_pull(key='configuration_context'))
    # config_context['sql'][sql_id] = sql_query
    # kwargs['ti'].xcom_push(key='configuration_context', value=json.dumps(config_context))
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

    info                = json.loads(Variable.get("COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET"))
    credentials         = service_account.Credentials.from_service_account_info(info)
    gbq_client          = bigquery.Client(project=gcp_project_id, credentials=credentials)
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


def execute_bq_copy_table(  source_gcp_project_id, 
                            source_bq_dataset, 
                            source_bq_table, 
                            destination_gcp_project_id, 
                            destination_bq_dataset, 
                            destination_bq_table,
                            destination_bq_table_date_suffix,
                            destination_bq_table_date_suffix_format,
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
    info = json.loads(Variable.get("COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET"))
    credentials = service_account.Credentials.from_service_account_info(info)
    gbq_client = bigquery.Client(project="fd-jarvis-datalake", credentials=credentials)

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
                            **kwargs):


    logging.info("gcp_project_id : %s", gcp_project_id)
    logging.info("bq_dataset : %s", bq_dataset)
    logging.info("bq_table : %s", bq_table)
    
    # Create Bigquery client
    #
    info = json.loads(Variable.get("COMPOSER_SERVICE_ACCOUNT_CREDENTIALS_SECRET"))
    credentials = service_account.Credentials.from_service_account_info(info)
    gbq_client = bigquery.Client(project=gcp_project_id, credentials=credentials)

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
            
            return

    except exceptions.NotFound:
        logging.info("Table {} does not exist. Let's create it.".format(gcp_project_id + ":" + bq_dataset + "." + bq_table))

    except ValueError as error:
        logging.info(error)
        logging.info("Table {} exists and is not time partitioned.".format(gcp_project_id + ":" + bq_dataset + "." + bq_table))
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
            schemafield_to_add = fd_toolbox.process_bigquery_record(item)
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
    if (bq_table_timepartitioning_field is not None) or (bq_table_timepartitioning_expiration_ms is not None) or     (bq_table_timepartitioning_require_partition_filter is not None):

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


def build_sql_task(payload, env, default_gcp_project_id, default_bq_dataset, default_write_disposition, global_path):

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
        sql_doc += file.read().replace("`", "'").replace("\n", "\n\n")
        # print(sql_doc)

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


def build_copy_bq_table_task(payload, default_gcp_project_id, default_bq_dataset):

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

    destination_bq_table_date_suffix = "False"
    destination_bq_table_date_suffix_format = ""
    try:
        destination_bq_table_date_suffix = str(payload["destination_bq_table_date_suffix"])
        destination_bq_table_date_suffix_format = payload["destination_bq_table_date_suffix_format"].strip()
    except KeyError:
        print()

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


def build_create_bq_table_task(payload, default_gcp_project_id, default_bq_dataset, global_path):

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
        payload_ddl = json.load(f)

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
    # "bq_table_timepartitioning_field" : """ + str(bq_table_timepartitioning_field.strip()) + """,

    return output_payload


def build_vm_launcher_task(payload, gcp_project_id):

    # Infos
    #
    print("Generating VM LAUNCHER task ...")

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


def process(args):

    # Infos
    #
    print("Generating and deploying DAG ...")

    # Retrieving arguments
    #
    input_filename = args.arguments[0]
    print("File to process      : {}".format(input_filename))
    if len(args.arguments) >= 2:
        environment = args.arguments[1]
    else:
        environment = "PROD"

    # Open JSON configuration file
    #
    json_file = open(input_filename, "r")
    json_payload = json.load(json_file)
    json_file.close()

    # Get path of filename
    #
    global_path = jarvis_misc.get_path_from_file(input_filename)

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

    # Start building the payload
    # build the header
    #
    output_payload = build_header(dag_name, dag_start_date)

    # Add the different functions needed
    #
    output_payload += build_functions(dag_name, environment)

    # Main code
    #

    # Check for Schedule Interval
    #
    if json_payload["schedule_interval"] == "None":
        dag_schedule_interval = "None"
    else:
        dag_schedule_interval = "\"" + json_payload["schedule_interval"] + "\""

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
    # Process all the tasks
    #
    for item in json_payload["workflow"]:

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
                item, default_gcp_project_id, default_bq_dataset)

        elif task_type == "create_gbq_table":
            generated_code = build_create_bq_table_task(
                item, default_gcp_project_id, default_bq_dataset, global_path)

        elif task_type == "vm_launcher":
            generated_code = build_vm_launcher_task(item, default_gcp_project_id)

        else:
            generated_code = build_sql_task(
                item, environment, default_gcp_project_id, default_bq_dataset, default_write_disposition, global_path)

        # Add the result to the main payload
        #
        output_payload += generated_code + "\n"

    # Add "initialize" function
    # Add PubSub logging
    #
    output_payload += build_complementary_code()

    # Add task dependencies
    #
    output_payload += """
    # Task dependencies
    #
    send_dag_infos_to_pubsub_start >> initialize >> send_dag_infos_to_pubsub_after_config
    initialize >> send_dag_infos_to_pubsub_deactivated
"""
    if len(dag_task_dependencies) > 0:
        for index in range(0, len(dag_task_dependencies)):
            output_payload += "    " + dag_task_dependencies[index] + "\n"

    # Add the task "send_dag_infos_to_pubsub" as the last task
    #
    for item in json_payload["workflow"]:
        output_payload += """    """ + \
            item["id"] + """ << send_dag_infos_to_pubsub_after_config\n\r"""
        output_payload += """    """ + \
            item["id"] + """ >> send_dag_infos_to_pubsub\n\r"""
        output_payload += """    """ + \
            item["id"] + """ >> send_dag_infos_to_pubsub_failed\n\r"""

    collection = "gbq-to-gbq-conf"
    doc_id = dag_name

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

    # pp = pprint.PrettyPrinter(indent=4)
    # pp.pprint(data)

    #Debug
    #
    # with open("test.py", "w") as outfile:
    #     outfile.write(output_payload)

    # return

    #######################
    # Prepare call to API #
    #######################

    # Get configuration
    #
    jarvis_configuration = jarvis_config.get_jarvis_configuration_file()

    # Get firebase user
    #
    firebase_user = jarvis_auth.get_refreshed_firebase_user(jarvis_configuration)

    # Get list of project profiles open to the user and ask him to pick one
    #
    ret_code, project_profile = jarvis_misc.choose_project_profiles(jarvis_configuration, firebase_user)
    if ret_code is False:
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

        r = requests.put(url, headers=headers, data=json.dumps(payload))

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
