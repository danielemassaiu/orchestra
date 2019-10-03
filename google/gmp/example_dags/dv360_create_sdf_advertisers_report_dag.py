###########################################################################
#
#  Copyright 2018 Google Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
###########################################################################
"""Example DAG which creates DV360 report."""
from datetime import datetime
from datetime import timedelta
from airflow import DAG
from airflow import models
from google.gmp.operators.gmp_dv360_operator import DisplayVideo360CreateReportOperator
from google.gmp.operators.gmp_dv360_operator import DisplayVideo360RunReportOperator
from google.gmp.sensors.gmp_dv360_sensor import DisplayVideo360ReportSensor
from google.gmp.operators.gmp_dv360_operator import DisplayVideo360DeleteReportOperator
from google.gmp.operators.gmp_dv360_operator import DisplayVideo360SDFAdvertiserFromReportOperator


CONN_ID = "gmp_reporting"
REPORT = """{
    "kind": "doubleclickbidmanager#query",
    "metadata": {
        "title": "Advertiser IDs",
        "dataRange": "LAST_30_DAYS",
        "format": "CSV",
        "sendNotification": False
    },
    "params": {
        "type": "TYPE_GENERAL",
        "groupBys": ["FILTER_ADVERTISER", "FILTER_PARTNER"],
        "filters": [
        {%- for partner in params.partners %}
            {% if not loop.first %}, {% endif -%}
            {"type": "FILTER_PARTNER", "value": {{ partner }}}
        {%- endfor -%}
        ],
        "metrics": ["METRIC_IMPRESSIONS"],
        "includeInviteData": True
    },
    "schedule": {
        "frequency": "ONE_TIME",
    }
}"""


def yesterday():
  return datetime.today() - timedelta(days=1)


default_args = {
    "owner": "airflow",
    "start_date": yesterday(),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(seconds=10),
}


dag = DAG(
    "dv360_create_sdf_advertisers_report_dag",
    default_args=default_args,
    schedule_interval=None)

partner_ids = models.Variable.get("partner_ids").split(",")
create_report = DisplayVideo360CreateReportOperator(
    task_id="create_report",
    gcp_conn_id=CONN_ID,
    report=REPORT,
    params={"partners": partner_ids},
    dag=dag)
query_id = "{{ task_instance.xcom_pull('create_report', key='query_id') }}"

run_report = DisplayVideo360RunReportOperator(
    task_id="run_report",
    gcp_conn_id=CONN_ID,
    query_id=query_id,
    dag=dag)

wait_for_report = DisplayVideo360ReportSensor(
    task_id="wait_for_report",
    gcp_conn_id=CONN_ID,
    query_id=query_id,
    dag=dag)
report_url = "{{ task_instance.xcom_pull('wait_for_report', key='report_url') }}"

extract_advertisers = DisplayVideo360SDFAdvertiserFromReportOperator(
    task_id='extract_advertisers',
    conn_id=CONN_ID,
    depends_on_past=False,
    report_url=report_url,
    dag=dag)

delete_report = DisplayVideo360DeleteReportOperator(
    task_id="delete_report",
    gcp_conn_id=CONN_ID,
    query_id=query_id,
    dag=dag)

create_report >> run_report >> wait_for_report >> extract_advertisers >> delete_report
