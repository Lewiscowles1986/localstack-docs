import csv
import os
import sys
from pathlib import Path
import json
from json import JSONDecodeError

def create_metric_coverage_docs(file_name: str, metrics: dict):
    if os.path.exists(file_name):
        os.remove(file_name)

    

    for service in sorted(metrics.keys()):
        #output += f"## {service} ##\n\n"
        if service != 'dynamodb':
            continue

        DOCS_HEADER = f"""---
title: "LocalStack Coverage {service} #new"
linkTitle: "LocalStack Coverage {service} #new"
weight: 100
description: >
  Overview of the implemented AWS APIs in LocalStack
hide_readingtime: true
---
\n\n
"""

        TABLE_HEADER = """
        <thead>
            <tr>
            <th>Operation</th>
            <th style="text-align:right">Implemented</th>
            </tr>
        </thead>"""


        details = ""
        output = DOCS_HEADER
        output += '<div class="coverage-report">\n\n'
        header = f"""<table><thead>
        <tr>
        <th>Operation</th>
        <th>Implemented</th>
        <th>Availability</th>
        <th>LS Integration Tested</th>
        <th>Moto Integration Tested</th>
        <th>AWS Validated</th>
        <th>Snapshot Tested</th>
        <th>Details</th>
        </tr>
    </thead>
    <tbody>"""
        output += header
                
        output += "  <tbody>\n"

        show_details = "\n\n## Details"
        for operation in sorted(metrics.get(service).keys()):
            op_details = metrics.get(service).get(operation)

            if op_details.get("implemented"):
                ls_tested = False
                moto_tested = False
                aws_validated = False
                snapshot_tested = False
                snapshot_skipped = False
                if op_details.get("invoked", 0) > 0:
                    source = op_details.get("source",[])
                    if "community-integration-test" in source or "pro-integration-test" in source:
                        ls_tested = True
                    if "moto-integration-test" in source:
                        moto_tested= True
                    if op_details.get("aws_validated"):
                        aws_validated = True
                    if op_details.get("snapshot"):
                        aws_validated = True
                        skipped_path = op_details.get('snapshot_skipped_paths', '')
                        if skipped_path == "all":
                            # we set "all" if there was not path, e.g. the entire snapshot verification is skipped
                            # we do not consider it as "snapshot tested" then
                            snapshot_tested = False
                        elif skipped_path:
                            snapshot_skipped = True
                            snapshot_tested = True
                details = f"""<tr>
                <td>{operation}</td>
                <td class="coverage-operation-details-icon">{"✅" if op_details.get("implemented") else ""}</td>
                <td>{"Pro" if op_details.get("pro") else "Community"}</td>
                <td class="coverage-operation-details-icon">{"✅" if ls_tested else ""}</td>
                <td class="coverage-operation-details-icon">{"✅" if moto_tested else ""}</td>
                <td class="coverage-operation-details-icon">{"✅" if aws_validated else ""}</td>
                <td class="coverage-operation-details-icon">{"✅" if snapshot_tested else ""}</td>
                <td><a href=#{operation.lower()}>Show details</a></td>
                </tr>
                """
                test_details = ""
                # "parameter_combination": {"param_identifier": {"params":"param1, param2","tests": {"node_id": {"snapshot": True, "skipped_path": "all"}},"response":200, "error": "exception")}
                test_details += "#### Parameter Combinations Tested\n\n"
                for _, detail in sorted(op_details.get("parameter_combination",{}).items()):
                    
                    test_details += f" * **{detail.get('params')}**\n"
                    test_details += f"   * Response: {detail.get('response')}{' (' + detail.get('error') +')' if detail.get('error') else ''}\n"
                    test_details += "   * Tests:\n"""
                    for node_id, node_details in sorted(detail.get("tests").items()):
                        test_details += f"     * {node_id}\n"
                        skipped_paths = node_details.get('skipped_path')
                        if node_details.get('aws_validated') or node_details.get("snapshot"): 
                            test_details += f"       * AWS validated{', Snapshot test' if node_details.get('snapshot') and  skipped_paths is not 'all' else ''}{' (some snapshot validation excluded)' if skipped_paths else ''}\n"

                    test_details += "\n\n"
                show_details += f"""
### {operation}

{test_details}
"""
            else:
                details = f"""<tr>
                <td class="coverage-operation-not-implemented">{operation}</td>
                <td></td>
                <td></td>
                <td></td>
                <td></td>
                <td></td>
                <td></td>
                <td></td>
                </tr>
                """
            output += details


    output += "   <tbody>\n"
    output += " </table>\n\n"
    output += "\n\n</div>"
    output += show_details
    with open(file_name, "a") as fd:
        fd.write(f"{output}\n")
        # fd.write(
        #     "## Misc ##\n\n" "Endpoints marked with ✨ are covered by our integration test suite.\n"
        # )
        # fd.write("The 💫 indicates that moto integration tests cover the endpoint, and run succesfully against LocalStack.")
    
    print(f"--> file: {file_name}")




def main(path_to_implementation_details: str, path_to_raw_metrics: str):
    impl_details = {}
    # read the implementation-details for pro + community first and generate a dict
    # with information about all services and operation, and indicator if those are implemented, and avaiable only in pro:
    # {"service_name": 
    #   {
    #       "operation_name": {"implemented": True, "pro": False}
    #   }
    # }
    with open(
        f"{path_to_implementation_details}/pro/implementation_coverage_full.csv", mode="r"
    ) as file:
        # check pro implementation details first
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            service = impl_details.setdefault(row["service"], {})
            service[row["operation"]] = {
                "implemented": True if row["is_implemented"] == "True" else False,
                "pro": True,
            }
    with open(
        f"{path_to_implementation_details}/community/implementation_coverage_full.csv", mode="r"
    ) as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            service = impl_details.setdefault(row["service"], {})
            # update all operations that are available in community
            if row["is_implemented"] == "True":
                service[row["operation"]]["pro"] = False 

    # now check the actual recorded test data and map the information
    recorded_metrics = aggregate_recorded_raw_data(
        base_dir=path_to_raw_metrics, service_dict=impl_details
    )

    # create the coverage-docs
    create_metric_coverage_docs(
        file_name=path_to_raw_metrics + "/coverage.md", metrics=recorded_metrics
    )


def _init_metric_recorder(service_dict: dict):
    """
    creates the base structure to collect raw data from the service_dict
    :param service_dict: 
    """
    recorder = {}
    for service, ops in service_dict.items():
        operations = {}
        for operation, details in ops.items():
            attributes = {
                "implemented": details["implemented"],
                "pro": details["pro"],
                "invoked": 0,
                "aws_validated": False,
                "snapshot": False,
                "parameters": {},
                "errors": {},
            }
            operations[operation] = attributes
        recorder[service] = operations
    return recorder


def aggregate_recorded_raw_data(base_dir: str, service_dict: dict):
    """
    collects all the raw metric data and maps them in a dict:
        { "service_name":
            {"operation-name":
                {"invoked": 0,
                "aws_validated": False,
                "snapshot": False,
                "parameter_combination": {"param_identifier": {"params":[param1, param2],"test": {"node_id": {"snapshot": True, "skipped_path": "all"}},"response":200, "error": "exception")},
                "source": [] },
            ....
            },
            ...
        }
    :param base_dir: directory where the raw-metrics csv-files are stored
    :param service_dict: dict 

    :returns: dict with details about invoked operations
    """
    # TODO contains internal + external
    recorded_data = _init_metric_recorder(service_dict)
    pathlist = Path(base_dir).rglob("*.csv")
    for path in pathlist:
        test_source = path.stem
        print(f"checking {str(path)}")
        with open(path, "r") as csv_obj:
            csv_dict_reader = csv.DictReader(csv_obj)
            for metric in csv_dict_reader:
                node_id = metric.get("node_id") or metric.get("test_node_id")

                # skip tests are marked as xfail
                if str(metric.get("xfail", "")).lower() == "true":
                    continue
                
                # TODO skipping "internal" seems to lower the coverage now, because some tests use e.g. cfn other implicit calls
                # to verify behavior -> takle this issue in the next iteration
                #if metric.get("origin").lower() == "internal":
                #    # exclude all internal service calls, those might be false positives for aws-validated tests
                #    continue

                service = recorded_data.get(metric.get("service"))
                # some metrics (e.g. moto) could include tests for services, we do not support
                if not service:
                    print(f"---> service {metric.get('service')} was not found")
                    continue
                ops = service.get(metric.get("operation"))
                if not ops:
                    print(f"---> operation {metric.get('service')}.{metric.get('operation')} was not found")
                    continue
                

                if param_exception := metric.get("exception", ""):
                    if param_exception == "CommonServiceException":
                        try:
                            data = json.loads(metric.get("response_data","{}"))
                            param_exception = data.get("__type", param_exception)
                        except JSONDecodeError:
                            print(f"{metric.get('service')}: could not decode CommonServiceException details")
                            

                if str(metric.get("snapshot", "false")).lower() == "true":
                    if ops.get("snapshot") == True:
                        # only update snapshot_skipped_paths if necessary (we prefer the test record where nothing was skipped)
                        ops["snapshot_skipped_paths"] = "" if metric.get("snapshot_skipped_paths", "") else ops.get("snapshot_skipped_paths", "") 
                    else:
                        ops["snapshot"] = True  # TODO snapshot currently includes also "skip_verify"
                        ops["snapshot_skipped_paths"] = metric.get("snapshot_skipped_paths", "") 

                if str(metric.get("aws_validated", "false")).lower() == "true":
                    ops["aws_validated"] = True

                parameter_combination = ops.setdefault("parameter_combination", {})
                test_node_origin = ""
                if test_source.startswith("community"):
                    test_node_origin = "LocalStack Community"
                elif test_source.startswith("pro"):
                    test_node_origin = "LocalStack Pro"
                elif test_source.startswith("moto"):
                    test_node_origin = "Moto"

                test_node_id = f"{test_node_origin}: {node_id}"

                params = metric.get("parameters", "None").split(",")
                params.sort()

                parameters = ", ".join(params)
                response_code = int(metric.get("response_code", -1))
                param_comb_key = f"{parameters}:{response_code}"


                param_details = parameter_combination.setdefault(param_comb_key, {})
                if not param_details:
                    param_details["params"] = parameters
                    param_details["response"] = response_code
                    param_details["error"] =  param_exception

                node_ids = param_details.setdefault("tests", {})
                # remove parametrized info from node id, as it will have the same attributes
                cur_node_id_simple = test_node_id.split("[")[0]
                node_ids[cur_node_id_simple] = {"snapshot": metric.get("snapshot", "false").lower() == "true",
                                                "skipped_path": metric.get("snapshot_skipped_paths", ""),
                                                "aws_validated": str(metric.get("aws_validated", "false")).lower() == "true"}
                
                # "parameter_combination": {"param_identifier": {"params":"param1, param2","tests": {"node_id": {"snapshot": True, "skipped_path": "all"}},"response":200, "error": "exception")}



                source_list = ops.setdefault("source", [])
                if test_source not in source_list:
                    source_list.append(test_source)

    return recorded_data


def print_usage():
    print("missing arguments")
    print(
        "usage: python coverage_docs_utility.py <dir-to-implementation-details> <dir-to-raw-csv-metric>"
    )


if __name__ == "__main__":
    if len(sys.argv) != 3 or not Path(sys.argv[1]).is_dir() or not Path(sys.argv[2]).is_dir():
        print_usage()
    else:
        main(sys.argv[1], sys.argv[2])
