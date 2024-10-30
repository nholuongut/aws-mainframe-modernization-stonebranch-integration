# Author  : Vaidyanathan Ganesa Sankaran ; Huseyin Gomleksizoglu; Pablo Alonso Prieto; Praveen Kumar
# Date    : "05-Oct-2022"
# Version : extension.py: 20221005
#
# MIT No Attribution

# Copyright 2022 Amazon Web Services Inc ; Stonebranch Inc

# Permission is hereby granted, free of charge, to any person obtaining a copy of this
# software and associated documentation files (the "Software"), to deal in the Software
# without restriction, including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


from __future__ import print_function
from time import sleep
from platform import uname
import yaml
import sys
import re

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import requests
import json

from universal_extension import UniversalExtension
from universal_extension import ExtensionResult
from universal_extension.deco import dynamic_choice_command, dynamic_command
from universal_extension import ui


class Extension(UniversalExtension):
    """Required class that serves as the entry point for the extension"""

    base_url = None
    service = "m2"

    def __init__(self):
        """Initializes an instance of the 'Extension' class"""
        # Call the base class initializer
        super(Extension, self).__init__()

    def extension_start(self, fields):
        """Required method that serves as the starting point for work performed
        for a task instance.

        Parameters
        ----------
        fields : dict
            populated with field values from the associated task instance
            launched in the Controller

        Returns
        -------
        ExtensionResult
            once the work is done, an instance of ExtensionResult must be
            returned. See the documentation for a full list of parameters that
            can be passed to the ExtensionResult class constructor
        """

        self.intro(fields)
        self.fields = self.get_fields(fields)

        # Get the value of the 'action' field
        action = self.fields.action
        self.setup_aws(fields)

        self.rc = 0
        self.unv_output = "Task completed"
        if action == "list-applications":
            self.list_applications()
        elif action == "list-environments":
            self.list_environments()
        elif action == "start-batch":
            self.start_batch(fields)
        elif action == "fetch-logs":
            application_id = self.parse_application_id(self.fields.application)
            self.get_log_events(
                application_id,
                self.fields.filter_pattern,
                log_stream_name=self.fields.log_stream_name,
                format=self.fields.fetch_log_format,
            )
            # self.get_log_events_boto3(application_id, self.fields.filter_pattern)
        elif action == "start-application":
            application_id = self.parse_application_id(self.fields.application)
            self.start_application(application_id)
        elif action == "stop-application":
            application_id = self.parse_application_id(self.fields.application)
            self.stop_application(application_id)
        elif action == "cancel-batch-execution":
            application_id = self.parse_application_id(self.fields.application)
            self.cancel_batch_execution(
                application_id, self.fields.execution_id
            )
        elif action == "list-batch-jobs":
            application_id = self.parse_application_id(self.fields.application)
            self.list_batch_jobs(application_id)

        # Return the result with a payload containing a Hello message...
        self.log.info(f"extension_start function ended with rc = {self.rc}")
        return ExtensionResult(rc=self.rc, unv_output=self.unv_output)

    @dynamic_choice_command("application")
    def get_applications(self, fields):
        """Get List of applications"""
        self.setup_aws(fields)
        url = self.get_aws_url("/applications")
        response = self.signed_request(
            method="GET", url=url, headers=self.headers
        )
        if response.status_code == 200:
            apps = []
            for app in response.json()["applications"]:
                self.log.debug(
                    f'Application: {app["name"]} - {app["applicationId"]}'
                )
                apps.append(f'{app["name"]} ({app["applicationId"]})')

            return ExtensionResult(
                rc=0,
                message="Supported Archive Formats: '{}'".format(apps),
                values=apps,
            )
        else:
            return ExtensionResult(
                rc=1,
                message="Failed to get the applications: '{}'".format(
                    response.text
                ),
                values=["failed"],
            )

    @dynamic_command("rerun")
    def rerun(self, fields):
        """Dynamic command implementation for rerun command.

        Parameters
        ----------
        fields : dict
            populated with the values of the dependent fields
        """

        # Reset the state of the Output Only 'step' fields.
        # out_fields = {}
        # out_fields["step_name"] = "Initial"
        # out_fields["procstep_name"] = "Initial"
        # out_fields["templib"] = "Initial"
        # ui.update_output_fields(out_fields)

        self.log.info(f"Fields = {fields}")

        return ExtensionResult(
            message=f"Message: Hello from dynamic command 'rerun'! Fields = {fields}",
            output=True,
            output_data=f"The batch rerun from the {fields}.",
            output_name="DYNAMIC_OUTPUT",
        )

    def setup_aws(self, fields):
        aws_access_key = fields.get("credentials.user", None)
        aws_secret_key = fields.get("credentials.password", None)
        self.region = fields.get("region", "us-east-1")

        session = boto3.Session(
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
        )
        credentials = session.get_credentials()
        self.creds = credentials.get_frozen_credentials()

        self.base_url = fields.get("end_point", "")
        if len(self.base_url) == 0:
            self.base_url = f"https://m2.{self.region}.amazonaws.com"

        self.headers = {
            "Content-Type": "application/x-amz-json-1.1",
            "Accept": "application/json",
        }

    def get_aws_url(self, url, service="m2"):
        if service == "m2":
            base_url = self.base_url
        elif service == "logs":
            base_url = f"https://logs.{self.region}.amazonaws.com"
        else:
            base_url = f"https://{service}.{self.region}.amazonaws.com"

        if base_url[-1] == "/":
            base_url = base_url[:-1]

        if url[0] != "/":
            url = "/" + url

        return base_url + url

    def signed_request(
        self, method, url, data=None, params=None, headers=None, service="m2"
    ):
        self.log.info(
            f"Signed request for {url} with header {headers} and data {data}"
        )
        request = AWSRequest(
            method=method, url=url, data=data, params=params, headers=headers
        )
        SigV4Auth(self.creds, service, self.region).add_auth(request)
        return requests.request(
            method=method, url=url, headers=dict(request.headers), data=data
        )

    def intro(self, fields: dict):
        self.log.debug(f"extension_start fields: {fields}")
        extension_yaml = yaml.safe_load(__loader__.get_data("extension.yml"))
        name = extension_yaml["extension"]["name"]
        version = extension_yaml["extension"]["version"]
        self.log.info(f"Extension Information: {name}-{version}")
        system, node, release, version, machine, processor = uname()
        self.log.info(
            f"System Information: Python Version: {sys.version}, system: {system},"
            f" release: {release}, version: {version}, machine type: {machine}"
        )

    def get_fields(self, fields):
        _fields = ExtensionFields(fields)
        self.log.info(f"FIELDS: {_fields}")
        return _fields

    def parse_application_id(self, application):
        result = re.match(r".* \((.*)\)", application)
        if result:
            return result.group(1)
        else:
            return None

    def list_applications(self):
        url = self.get_aws_url("/applications")
        response = self.signed_request(
            method="GET", url=url, headers=self.headers
        )
        if response.status_code == 200:
            for app in response.json()["applications"]:
                print(f'{app["name"]} - {app["applicationId"]}')
        else:
            self.log.error(
                f"Error while listing environments. Response body = {response.text}, status_code = {response.status_code}"
            )
            self.rc = 1
            self.unv_output = f"FAILED: Response body = {response.text}, status_code = {response.status_code}"
            return False

        self.log.info(f"Response = {response.text}")
        return True

    def list_environments(self):
        url = self.get_aws_url("/environments")
        response = self.signed_request(
            method="GET", url=url, headers=self.headers
        )
        if response.status_code == 200:
            for app in response.json()["environments"]:
                print(
                    f'{app["engineType"]} - {app["environmentId"]} - {app["name"]}'
                )
        else:
            self.log.error(
                f"Error while listing environments. Response body = {response.text}, status_code = {response.status_code}"
            )
            self.rc = 1
            self.unv_output = f"FAILED: Response body = {response.text}, status_code = {response.status_code}"
            return False

        self.log.info(f"Response = {response.text}")
        return True

    def list_batch_jobs(self, application_id):
        self.log.debug(f"application_id = {application_id}")
        url = self.get_aws_url(
            f"/applications/{application_id}/batch-job-definitions"
        )
        response = self.signed_request(
            method="GET", url=url, headers=self.headers
        )
        if response.status_code == 200:
            for app in response.json()["batchJobDefinitions"]:
                file_definition = app.get("fileBatchJobDefinition", None)
                if file_definition is not None:
                    print(
                        f'FILE: {file_definition["folderPath"]}/{file_definition["fileName"]}'
                    )
                script_definition = app.get("scriptBatchJobDefinition", None)
                if script_definition is not None:
                    print(f'SCRIPT: {script_definition["scriptName"]}')
        else:
            self.log.error(
                f"Error while listing batch jobs. Response body = {response.text}, status_code = {response.status_code}"
            )
            self.rc = 1
            self.unv_output = f"FAILED: Response body = {response.text}, status_code = {response.status_code}"
            return False

        self.log.info(f"Response = {response.text}")
        return True

    def start_application(self, application_id):
        self.log.debug(f"application_id = {application_id}")
        url = self.get_aws_url(f"/applications/{application_id}/start")
        response = self.signed_request(
            method="POST", url=url, data=None, headers=self.headers
        )
        if response.status_code == 200:
            self.log.debug(f"Response = {response.text}")
            if self.fields.wait:
                last_status_text = self.wait_for_application(application_id)
                if self.fields.fetch_logs:
                    self.get_log_events(
                        application_id,
                        execution_id="",
                        format=self.fields.log_format,
                    )
                else:
                    print(last_status_text)
        else:
            self.log.error(
                f"Error while starting the application. Response body = {response.text}, status_code = {response.status_code}"
            )
            self.rc = 1
            self.unv_output = f"FAILED: Response body = {response.text}, status_code = {response.status_code}"
            if self.fields.fetch_logs:
                self.get_log_events(
                    application_id,
                    execution_id="",
                    format=self.fields.log_format,
                )
            return False

        self.rc = 0
        self.unv_output = "Application successfully started."
        return True

    def stop_application(self, application_id):
        self.log.debug(f"application_id = {application_id}")
        url = self.get_aws_url(f"/applications/{application_id}/stop")
        payload = {"forceStop": self.fields.force_stop}
        json_payload = json.dumps(payload)
        response = self.signed_request(
            method="POST", url=url, data=json_payload, headers=self.headers
        )
        if response.status_code == 200:
            self.log.debug(f"Response = {response.text}")
            if self.fields.wait:
                last_status_text = self.wait_for_application(application_id)
                if self.fields.fetch_logs:
                    self.get_log_events(
                        application_id,
                        execution_id="",
                        format=self.fields.log_format,
                    )
                else:
                    print(last_status_text)
        else:
            self.log.error(
                f"Error while stopping the application. Response body = {response.text}, status_code = {response.status_code}"
            )
            self.rc = 1
            self.unv_output = f"FAILED: Response body = {response.text}, status_code = {response.status_code}"
            if self.fields.fetch_logs:
                self.get_log_events(
                    application_id,
                    execution_id="",
                    format=self.fields.log_format,
                )
            return False

        self.rc = 0
        self.unv_output = "Application successfully stopped."
        return True

    def cancel_batch_execution(self, application_id, execution_id):
        self.log.debug(
            f"application_id = {application_id} execution_id = {execution_id}"
        )
        url = self.get_aws_url(
            f"/applications/{application_id}/batch-job-executions/{execution_id}/cancel"
        )
        response = self.signed_request(
            method="POST", url=url, data=None, headers=self.headers
        )
        if response.status_code == 200:
            self.log.debug(f"Response = {response.text}")
            if self.fields.wait:
                last_status_text = self.wait_for_success(
                    application_id, execution_id
                )
                if self.fields.fetch_logs:
                    self.get_log_events(
                        application_id,
                        execution_id,
                        format=self.fields.log_format,
                    )
                else:
                    print(last_status_text)
        else:
            self.log.error(
                f"Error while cancelling the batch execution. Response body = {response.text}, status_code = {response.status_code}"
            )
            self.rc = 1
            self.unv_output = f"FAILED: Response body = {response.text}, status_code = {response.status_code}"
            if self.fields.fetch_logs:
                self.get_log_events(
                    application_id, execution_id, format=self.fields.log_format
                )
            return False

        self.rc = 0
        self.unv_output = "Batch execution successfully cancelled."
        return True

    def start_batch(self, fields):
        application_id = self.parse_application_id(
            fields.get("application")[0]
        )
        self.log.debug(f"application_id = {application_id}")

        jcl_file_name = fields.get("jcl_file_name")
        jcl_file_name_temp = fields.get("jcl_file_name_temp")
        if len(jcl_file_name_temp) > 0:
            jcl_file_name = jcl_file_name_temp

        payload = {"batchJob": {"jclFileName": jcl_file_name}}
        json_payload = json.dumps(payload)
        header = {"Content-Type": "application/json"}
        self.log.debug(f"Payload is {payload}")

        url = self.get_aws_url(f"/applications/{application_id}/batch-job")
        response = self.signed_request(
            method="POST", url=url, data=json_payload, headers=header
        )
        if response.status_code == 200:
            self.log.debug(f"Response = {response.text}")
            response_json = response.json()
            execution_id = response_json.get("executionId", "not_found")
            if execution_id == "not_found":
                self.rc = 2
                self.unv_output = f"FAILED while parsing response! Response body = {response.text}, status_code = {response.status_code}"
        else:
            execution_id = "Failed"
            self.log.error(
                f"Error while running batch job. Response body = {response.text}, status_code = {response.status_code}"
            )
            self.rc = 1
            self.unv_output = f"FAILED: Response body = {response.text}, status_code = {response.status_code}"

        out_fields = {
            "batch_execution_id": execution_id,
            "application_id": application_id,
        }
        ui.update_output_fields(out_fields)
        if self.fields.wait and self.rc == 0:
            last_status_text = self.wait_for_success(
                application_id, execution_id
            )
            if self.fields.fetch_logs:
                self.get_log_events(
                    application_id, execution_id, format=self.fields.log_format
                )
            else:
                print(last_status_text)
        return application_id, execution_id

    def wait_for_success(self, application_id, execution_id):
        if execution_id not in ["not_found", "Failed"]:
            completed = False
            while not completed:
                url = self.get_aws_url(
                    f"/applications/{application_id}/batch-job-executions/{execution_id}"
                )
                response = self.signed_request(
                    method="GET", url=url, headers=self.headers
                )
                response_json = response.json()
                completed = (
                    True
                    if response_json.get("status")
                    in [
                        "Cancelled",
                        "Succeeded",
                        "Failed",
                        "Succeeded With Warning",
                    ]
                    else False
                )
                if not completed:
                    sleep(self.fields.interval)

            aws_status = response_json.get("status")
            if aws_status == "Cancelled":
                self.rc = 103
            elif aws_status == "Failed":
                self.rc = 104

            if aws_status in ["Cancelled", "Failed"]:
                self.unv_output = f"Task failed because of the status of the AWS Batch Job Status. Status = {aws_status}"
            elif aws_status == "Succeeded With Warning":
                self.unv_output = (
                    "Task completed successfully but there are some warnings."
                )
            elif aws_status == "Succeeded":
                self.unv_output = "Task completed successfully."

            if not self.fields.fetch_logs:
                print(response.text)

    def wait_for_application(self, application_id):
        completed = False
        while not completed:
            url = self.get_aws_url(f"/applications/{application_id}")
            response = self.signed_request(
                method="GET", url=url, headers=self.headers
            )
            response_json = response.json()
            completed = (
                True
                if response_json.get("status")
                in ["Running", "Stopped", "Failed"]
                else False
            )
            if not completed:
                sleep(self.fields.interval)

        aws_status = response_json.get("status")
        if aws_status == "Stopped":
            self.rc = 103
        elif aws_status == "Failed":
            self.rc = 104

        # Creating | Created | Available | Ready | Starting | Running | Stopping | Stopped | Failed | Deleting
        if aws_status in ["Stopped", "Failed"]:
            self.unv_output = f"Task failed because of the status of the Application. Status = {aws_status}"
        elif aws_status == "Running":
            self.unv_output = (
                "Task completed successfully. Application is running."
            )

        if not self.fields.fetch_logs:
            print(response.text)

    def get_log_events(
        self,
        application_id,
        execution_id="",
        log_stream_name="*",
        format="text",
    ):
        group_name = f"/aws/vendedlogs/m2/{application_id}/ConsoleLog"
        url = self.get_aws_url("/", service="logs")

        payload = {
            "logGroupName": group_name,
            "logStreamName": log_stream_name,
        }
        headers = self.headers.copy()
        headers["X-Amz-Target"] = "Logs_20140328.FilterLogEvents"
        if len(execution_id) > 0:
            payload["filterPattern"] = execution_id

        json_payload = json.dumps(payload)
        response = self.signed_request(
            method="POST",
            url=url,
            data=json_payload,
            headers=headers,
            service="logs",
        )
        if response.status_code == 200:
            self.log.debug(f"Response = {response.text}")
            try:
                self.log.info(f"Log format = {format}")
                if format == "json":
                    content = json.dumps(
                        response.json(), indent=4, sort_keys=True
                    )
                    print(content)
                else:
                    for event in response.json().get("events", []):
                        print(event.get("message"))
            except:
                content = response
                self.log.error(
                    f"Error while running batch job. Response body = {response.text}, status_code = {response.status_code}"
                )
                self.rc = 1
                self.unv_output = f"FAILED: Response body = {response.text}, status_code = {response.status_code}"
                return False

            return True
        else:
            self.log.error(
                f"Error while running batch job. Response body = {response.text}, status_code = {response.status_code}"
            )
            self.rc = 1
            self.unv_output = f"FAILED: Response body = {response.text}, status_code = {response.status_code}"
            return False


class ExtensionFields:
    def __init__(self, fields) -> None:
        self.action = fields.get("action", [None])[0]
        self.credentials = {
            "user": fields.get("credentials.user", None),
            "password": fields.get("credentials.password", None),
        }
        self.end_point = fields.get("end_point", None)
        self.region = fields.get("region", None)
        self.application = fields.get("application", [None])[0]
        self.jcl_file_name = fields.get("jcl_file_name", None)
        self.jcl_file_name_temp = fields.get("jcl_file_name_temp", None)
        self.wait = fields.get("wait", False)
        self.interval = fields.get("interval", 10)
        self.fetch_logs = fields.get("fetch_logs", False)
        self.fetch_log_format = fields.get("fetch_log_format", [None])[0]
        self.file_path = fields.get("file_path", None)
        self.step_name = fields.get("step_name", None)
        self.procstep_name = fields.get("procstep_name", None)
        self.templib = fields.get("templib", None)
        self.filter_pattern = fields.get("filter_pattern", "")
        self.log_stream_name = fields.get("log_stream_name", "*")
        self.log_format = fields.get("log_format", ["text"])[0]
        self.execution_id = fields.get("execution_id", None)
        self.force_stop = fields.get("force_stop", False)

    def __str__(self):
        return {
            "application": self.application,
            "credentials": self.credentials,
        }.__str__()
