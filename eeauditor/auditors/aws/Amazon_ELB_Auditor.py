#This file is part of ElectricEye.
#SPDX-License-Identifier: Apache-2.0

#Licensed to the Apache Software Foundation (ASF) under one
#or more contributor license agreements.  See the NOTICE file
#distributed with this work for additional information
#regarding copyright ownership.  The ASF licenses this file
#to you under the Apache License, Version 2.0 (the
#"License"); you may not use this file except in compliance
#with the License.  You may obtain a copy of the License at

#http://www.apache.org/licenses/LICENSE-2.0

#Unless required by applicable law or agreed to in writing,
#software distributed under the License is distributed on an
#"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#KIND, either express or implied.  See the License for the
#specific language governing permissions and limitations
#under the License.

import tomli
import os
import sys
import boto3
import ipaddress
import datetime
import base64
import json
from botocore.exceptions import ClientError
from check_register import CheckRegister
from security import safe_requests

registry = CheckRegister()

registry = CheckRegister()

SHODAN_HOSTS_URL = "https://api.shodan.io/shodan/host/"

def get_shodan_api_key(cache):

    response = cache.get("get_shodan_api_key")
    if response:
        return response

    validCredLocations = ["AWS_SSM", "AWS_SECRETS_MANAGER", "CONFIG_FILE"]

    # Get the absolute path of the current directory
    currentDir = os.path.abspath(os.path.dirname(__file__))
    # Go two directories back to /eeauditor/
    twoBack = os.path.abspath(os.path.join(currentDir, "../../"))

    # TOML is located in /eeauditor/ directory
    tomlFile = f"{twoBack}/external_providers.toml"
    with open(tomlFile, "rb") as f:
        data = tomli.load(f)

    # Parse from [global] to determine credential location of PostgreSQL Password
    credLocation = data["global"]["credentials_location"]
    shodanCredValue = data["global"]["shodan_api_key_value"]
    if credLocation not in validCredLocations:
        print(f"Invalid option for [global.credLocation]. Must be one of {str(validCredLocations)}.")
        sys.exit(2)
    if not shodanCredValue:
        apiKey = None
    else:

        # Boto3 Clients
        ssm = boto3.client("ssm")
        asm = boto3.client("secretsmanager")

        # Retrieve API Key
        if credLocation == "CONFIG_FILE":
            apiKey = shodanCredValue

        # Retrieve the credential from SSM Parameter Store
        elif credLocation == "AWS_SSM":
            
            try:
                apiKey = ssm.get_parameter(
                    Name=shodanCredValue,
                    WithDecryption=True
                )["Parameter"]["Value"]
            except ClientError as e:
                print(f"Error retrieving API Key from SSM, skipping all Shodan checks, error: {e}")
                apiKey = None

        # Retrieve the credential from AWS Secrets Manager
        elif credLocation == "AWS_SECRETS_MANAGER":
            try:
                apiKey = asm.get_secret_value(
                    SecretId=shodanCredValue,
                )["SecretString"]
            except ClientError as e:
                print(f"Error retrieving API Key from ASM, skipping all Shodan checks, error: {e}")
                apiKey = None
        
    cache["get_shodan_api_key"] = apiKey
    return cache["get_shodan_api_key"]

def google_dns_resolver(target):
    """
    Accepts a Public DNS name and attempts to use Google's DNS A record resolver to determine an IP address
    """
    url = f"https://dns.google/resolve?name={target}&type=A"
    
    r = safe_requests.get(url=url)
    if r.status_code != 200:
        return None
    else:
        for result in json.loads(r.text)["Answer"]:
            try:
                if not (
                    ipaddress.IPv4Address(result["data"]).is_private
                    or ipaddress.IPv4Address(result["data"]).is_loopback
                    or ipaddress.IPv4Address(result["data"]).is_link_local
                ):
                    return result["data"]
                else:
                    continue
            except ipaddress.AddressValueError:
                continue
        # if the loop terminates without any result return None
        return None

def describe_clbs(cache, session):
    response = cache.get("describe_load_balancers")
    if response:
        return response
    
    elb = session.client("elb")

    cache["describe_load_balancers"] = elb.describe_load_balancers()["LoadBalancerDescriptions"]
    return cache["describe_load_balancers"]

@registry.register_check("elasticloadbalancing")
def internet_facing_clb_https_listener_check(cache: dict, session, awsAccountId: str, awsRegion: str, awsPartition: str) -> dict:
    """[ELB.1] Classic load balancers that are internet-facing should use secure listeners"""
    # ISO Time
    iso8601Time = (datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat())
    for lb in describe_clbs(cache, session):
        # B64 encode all of the details for the Asset
        assetJson = json.dumps(lb,default=str).encode("utf-8")
        assetB64 = base64.b64encode(assetJson)
        clbName = lb["LoadBalancerName"]
        clbArn = f"arn:{awsPartition}:elasticloadbalancing:{awsRegion}:{awsAccountId}:loadbalancer/{clbName}"
        dnsName = lb["DNSName"]
        lbSgs = lb["SecurityGroups"]
        lbSubnets = lb["Subnets"]
        lbAzs = lb["AvailabilityZones"]
        lbVpc = lb["VPCId"]
        clbScheme = lb["Scheme"]
        if clbScheme == "internet-facing":
            for listeners in lb["ListenerDescriptions"]:
                if listeners["Listener"]["Protocol"] != "HTTPS" or "SSL":
                    finding = {
                        "SchemaVersion": "2018-10-08",
                        "Id": clbArn + "/classic-loadbalancer-secure-listener-check",
                        "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                        "GeneratorId": clbArn,
                        "AwsAccountId": awsAccountId,
                        "Types": ["Software and Configuration Checks/AWS Security Best Practices"],
                        "FirstObservedAt": iso8601Time,
                        "CreatedAt": iso8601Time,
                        "UpdatedAt": iso8601Time,
                        "Severity": {"Label": "MEDIUM"},
                        "Confidence": 99,
                        "Title": "[ELB.1] Classic load balancers that are internet-facing should use secure listeners",
                        "Description": "Classic load balancer "
                        + clbName
                        + " does not use a secure listener (HTTPS or SSL). Refer to the remediation instructions to remediate this behavior",
                        "Remediation": {
                            "Recommendation": {
                                "Text": "For more information on classic load balancer HTTPS listeners refer to the Create a Classic Load Balancer with an HTTPS Listener section of the Classic Load Balancers User Guide.",
                                "Url": "https://docs.aws.amazon.com/elasticloadbalancing/latest/classic/elb-create-https-ssl-load-balancer.html",
                            }
                        },
                        "ProductFields": {
                            "ProductName": "ElectricEye",
                            "Provider": "AWS",
                            "ProviderType": "CSP",
                            "ProviderAccountId": awsAccountId,
                            "AssetRegion": awsRegion,
                            "AssetDetails": assetB64,
                            "AssetClass": "Networking",
                            "AssetService": "AWS Elastic Load Balancer",
                            "AssetComponent": "Classic Load Balancer"
                        },
                        "Resources": [
                            {
                                "Type": "AwsElbLoadBalancer",
                                "Id": clbArn,
                                "Partition": awsPartition,
                                "Region": awsRegion,
                                "Details": {
                                    "AwsElbLoadBalancer": {
                                        "DnsName": dnsName,
                                        "Scheme": clbScheme,
                                        "SecurityGroups": lbSgs,
                                        "Subnets": lbSubnets,
                                        "VpcId": lbVpc,
                                        "AvailabilityZones": lbAzs,
                                        "LoadBalancerName": clbName
                                    }
                                }
                            }
                        ],
                        "Compliance": {
                            "Status": "FAILED",
                            "RelatedRequirements": [
                                "NIST CSF V1.1 PR.DS-2",
                                "NIST SP 800-53 Rev. 4 SC-8",
                                "NIST SP 800-53 Rev. 4 SC-11",
                                "NIST SP 800-53 Rev. 4 SC-12",
                                "AICPA TSC CC6.1",
                                "ISO 27001:2013 A.8.2.3",
                                "ISO 27001:2013 A.13.1.1",
                                "ISO 27001:2013 A.13.2.1",
                                "ISO 27001:2013 A.13.2.3",
                                "ISO 27001:2013 A.14.1.2",
                                "ISO 27001:2013 A.14.1.3",
                            ],
                        },
                        "Workflow": {"Status": "NEW"},
                        "RecordState": "ACTIVE",
                    }
                    yield finding
                else:
                    finding = {
                        "SchemaVersion": "2018-10-08",
                        "Id": clbArn + "/classic-loadbalancer-secure-listener-check",
                        "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                        "GeneratorId": clbArn,
                        "AwsAccountId": awsAccountId,
                        "Types": ["Software and Configuration Checks/AWS Security Best Practices"],
                        "FirstObservedAt": iso8601Time,
                        "CreatedAt": iso8601Time,
                        "UpdatedAt": iso8601Time,
                        "Severity": {"Label": "INFORMATIONAL"},
                        "Confidence": 99,
                        "Title": "[ELB.1] Classic load balancers that are internet-facing should use secure listeners",
                        "Description": "Classic load balancer "
                        + clbName
                        + " uses a secure listener (HTTPS or SSL).",
                        "Remediation": {
                            "Recommendation": {
                                "Text": "For more information on classic load balancer HTTPS listeners refer to the Create a Classic Load Balancer with an HTTPS Listener section of the Classic Load Balancers User Guide.",
                                "Url": "https://docs.aws.amazon.com/elasticloadbalancing/latest/classic/elb-create-https-ssl-load-balancer.html",
                            }
                        },
                        "ProductFields": {
                            "ProductName": "ElectricEye",
                            "Provider": "AWS",
                            "ProviderType": "CSP",
                            "ProviderAccountId": awsAccountId,
                            "AssetRegion": awsRegion,
                            "AssetDetails": assetB64,
                            "AssetClass": "Networking",
                            "AssetService": "AWS Elastic Load Balancer",
                            "AssetComponent": "Classic Load Balancer"
                        },
                        "Resources": [
                            {
                                "Type": "AwsElbLoadBalancer",
                                "Id": clbArn,
                                "Partition": awsPartition,
                                "Region": awsRegion,
                                "Details": {
                                    "AwsElbLoadBalancer": {
                                        "DnsName": dnsName,
                                        "Scheme": clbScheme,
                                        "SecurityGroups": lbSgs,
                                        "Subnets": lbSubnets,
                                        "VpcId": lbVpc,
                                        "AvailabilityZones": lbAzs,
                                        "LoadBalancerName": clbName
                                    }
                                }
                            }
                        ],
                        "Compliance": {
                            "Status": "PASSED",
                            "RelatedRequirements": [
                                "NIST CSF V1.1 PR.DS-2",
                                "NIST SP 800-53 Rev. 4 SC-8",
                                "NIST SP 800-53 Rev. 4 SC-11",
                                "NIST SP 800-53 Rev. 4 SC-12",
                                "AICPA TSC CC6.1",
                                "ISO 27001:2013 A.8.2.3",
                                "ISO 27001:2013 A.13.1.1",
                                "ISO 27001:2013 A.13.2.1",
                                "ISO 27001:2013 A.13.2.3",
                                "ISO 27001:2013 A.14.1.2",
                                "ISO 27001:2013 A.14.1.3",
                            ],
                        },
                        "Workflow": {"Status": "RESOLVED"},
                        "RecordState": "ARCHIVED",
                    }
                    yield finding
        else:
            continue

@registry.register_check("elasticloadbalancing")
def clb_https_listener_tls12_policy_check(cache: dict, session, awsAccountId: str, awsRegion: str, awsPartition: str) -> dict:
    """[ELB.2] Classic load balancers should use TLS 1.2 listener policies"""
    # ISO Time
    iso8601Time = (datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat())
    for lb in describe_clbs(cache, session):
        # B64 encode all of the details for the Asset
        assetJson = json.dumps(lb,default=str).encode("utf-8")
        assetB64 = base64.b64encode(assetJson)
        clbName = lb["LoadBalancerName"]
        clbArn = f"arn:{awsPartition}:elasticloadbalancing:{awsRegion}:{awsAccountId}:loadbalancer/{clbName}"
        dnsName = lb["DNSName"]
        lbSgs = lb["SecurityGroups"]
        lbSubnets = lb["Subnets"]
        lbAzs = lb["AvailabilityZones"]
        lbVpc = lb["VPCId"]
        clbScheme = lb["Scheme"]
        for listeners in lb["ListenerDescriptions"]:
            listenerPolicies = listeners["PolicyNames"]
            if not listenerPolicies:
                continue
            elif "ELBSecurityPolicy-TLS-1-2-2017-01" in listenerPolicies:
                finding = {
                    "SchemaVersion": "2018-10-08",
                    "Id": clbArn + "/classic-loadbalancer-tls12-policy-check",
                    "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                    "GeneratorId": clbArn,
                    "AwsAccountId": awsAccountId,
                    "Types": ["Software and Configuration Checks/AWS Security Best Practices"],
                    "FirstObservedAt": iso8601Time,
                    "CreatedAt": iso8601Time,
                    "UpdatedAt": iso8601Time,
                    "Severity": {"Label": "INFORMATIONAL"},
                    "Confidence": 99,
                    "Title": "[ELB.2] Classic load balancers should use TLS 1.2 listener policies",
                    "Description": "Classic load balancer "
                    + clbName
                    + " does not use a TLS 1.2 listener policy.",
                    "Remediation": {
                        "Recommendation": {
                            "Text": "For more information on classic load balancer listener policies refer to the Predefined SSL Security Policies for Classic Load Balancers section of the Classic Load Balancers User Guide.",
                            "Url": "https://docs.aws.amazon.com/elasticloadbalancing/latest/classic/elb-security-policy-table.html",
                        }
                    },
                    "ProductFields": {
                        "ProductName": "ElectricEye",
                        "Provider": "AWS",
                        "ProviderType": "CSP",
                        "ProviderAccountId": awsAccountId,
                        "AssetRegion": awsRegion,
                        "AssetDetails": assetB64,
                        "AssetClass": "Networking",
                        "AssetService": "AWS Elastic Load Balancer",
                        "AssetComponent": "Classic Load Balancer"
                    },
                    "Resources": [
                        {
                            "Type": "AwsElbLoadBalancer",
                            "Id": clbArn,
                            "Partition": awsPartition,
                            "Region": awsRegion,
                            "Details": {
                                "AwsElbLoadBalancer": {
                                    "DnsName": dnsName,
                                    "Scheme": clbScheme,
                                    "SecurityGroups": lbSgs,
                                    "Subnets": lbSubnets,
                                    "VpcId": lbVpc,
                                    "AvailabilityZones": lbAzs,
                                    "LoadBalancerName": clbName
                                }
                            }
                        }
                    ],
                    "Compliance": {
                        "Status": "PASSED",
                        "RelatedRequirements": [
                            "NIST CSF V1.1 PR.DS-2",
                            "NIST SP 800-53 Rev. 4 SC-8",
                            "NIST SP 800-53 Rev. 4 SC-11",
                            "NIST SP 800-53 Rev. 4 SC-12",
                            "AICPA TSC CC6.1",
                            "ISO 27001:2013 A.8.2.3",
                            "ISO 27001:2013 A.13.1.1",
                            "ISO 27001:2013 A.13.2.1",
                            "ISO 27001:2013 A.13.2.3",
                            "ISO 27001:2013 A.14.1.2",
                            "ISO 27001:2013 A.14.1.3",
                        ],
                    },
                    "Workflow": {"Status": "RESOLVED"},
                    "RecordState": "ARCHIVED",
                }
                yield finding
            else:
                finding = {
                    "SchemaVersion": "2018-10-08",
                    "Id": clbArn + "/classic-loadbalancer-tls12-policy-check",
                    "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                    "GeneratorId": clbArn,
                    "AwsAccountId": awsAccountId,
                    "Types": ["Software and Configuration Checks/AWS Security Best Practices"],
                    "FirstObservedAt": iso8601Time,
                    "CreatedAt": iso8601Time,
                    "UpdatedAt": iso8601Time,
                    "Severity": {"Label": "MEDIUM"},
                    "Confidence": 99,
                    "Title": "[ELB.2] Classic load balancers should use TLS 1.2 listener policies",
                    "Description": "Classic load balancer "
                    + clbName
                    + " does not use a TLS 1.2 listener policy. Refer to the remediation instructions to remediate this behavior",
                    "Remediation": {
                        "Recommendation": {
                            "Text": "For more information on classic load balancer listener policies refer to the Predefined SSL Security Policies for Classic Load Balancers section of the Classic Load Balancers User Guide.",
                            "Url": "https://docs.aws.amazon.com/elasticloadbalancing/latest/classic/elb-security-policy-table.html",
                        }
                    },
                    "ProductFields": {
                        "ProductName": "ElectricEye",
                        "Provider": "AWS",
                        "ProviderType": "CSP",
                        "ProviderAccountId": awsAccountId,
                        "AssetRegion": awsRegion,
                        "AssetDetails": assetB64,
                        "AssetClass": "Networking",
                        "AssetService": "AWS Elastic Load Balancer",
                        "AssetComponent": "Classic Load Balancer"
                    },
                    "Resources": [
                        {
                            "Type": "AwsElbLoadBalancer",
                            "Id": clbArn,
                            "Partition": awsPartition,
                            "Region": awsRegion,
                            "Details": {
                                "AwsElbLoadBalancer": {
                                    "DnsName": dnsName,
                                    "Scheme": clbScheme,
                                    "SecurityGroups": lbSgs,
                                    "Subnets": lbSubnets,
                                    "VpcId": lbVpc,
                                    "AvailabilityZones": lbAzs,
                                    "LoadBalancerName": clbName
                                }
                            }
                        }
                    ],
                    "Compliance": {
                        "Status": "FAILED",
                        "RelatedRequirements": [
                            "NIST CSF V1.1 PR.DS-2",
                            "NIST SP 800-53 Rev. 4 SC-8",
                            "NIST SP 800-53 Rev. 4 SC-11",
                            "NIST SP 800-53 Rev. 4 SC-12",
                            "AICPA TSC CC6.1",
                            "ISO 27001:2013 A.8.2.3",
                            "ISO 27001:2013 A.13.1.1",
                            "ISO 27001:2013 A.13.2.1",
                            "ISO 27001:2013 A.13.2.3",
                            "ISO 27001:2013 A.14.1.2",
                            "ISO 27001:2013 A.14.1.3",
                        ],
                    },
                    "Workflow": {"Status": "NEW"},
                    "RecordState": "ACTIVE",
                }
                yield finding

@registry.register_check("elasticloadbalancing")
def clb_cross_zone_balancing_check(cache: dict, session, awsAccountId: str, awsRegion: str, awsPartition: str) -> dict:
    """[ELB.3] Classic load balancers should have cross-zone load balancing configured"""
    elb = session.client("elb")
    # ISO Time
    iso8601Time = (datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat())
    for lb in describe_clbs(cache, session):
        # B64 encode all of the details for the Asset
        assetJson = json.dumps(lb,default=str).encode("utf-8")
        assetB64 = base64.b64encode(assetJson)
        clbName = lb["LoadBalancerName"]
        clbArn = f"arn:{awsPartition}:elasticloadbalancing:{awsRegion}:{awsAccountId}:loadbalancer/{clbName}"
        dnsName = lb["DNSName"]
        lbSgs = lb["SecurityGroups"]
        lbSubnets = lb["Subnets"]
        lbAzs = lb["AvailabilityZones"]
        lbVpc = lb["VPCId"]
        clbScheme = lb["Scheme"]
        # Get Attrs
        response = elb.describe_load_balancer_attributes(LoadBalancerName=clbName)
        crossZoneCheck = str(
            response["LoadBalancerAttributes"]["CrossZoneLoadBalancing"]["Enabled"]
        )
        if crossZoneCheck == "False":
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": clbArn + "/classic-loadbalancer-cross-zone-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": clbArn,
                "AwsAccountId": awsAccountId,
                "Types": ["Software and Configuration Checks/AWS Security Best Practices"],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": "LOW"},
                "Confidence": 99,
                "Title": "[ELB.3] Classic load balancers should have cross-zone load balancing configured",
                "Description": "Classic load balancer "
                + clbName
                + " does not have cross-zone load balancing configured. Refer to the remediation instructions to remediate this behavior",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on cross-zone load balancing refer to the Configure Cross-Zone Load Balancing for Your Classic Load Balancer section of the Classic Load Balancers User Guide.",
                        "Url": "https://docs.aws.amazon.com/elasticloadbalancing/latest/classic/enable-disable-crosszone-lb.html",
                    }
                },
                "ProductFields": {
                    "ProductName": "ElectricEye",
                    "Provider": "AWS",
                    "ProviderType": "CSP",
                    "ProviderAccountId": awsAccountId,
                    "AssetRegion": awsRegion,
                    "AssetDetails": assetB64,
                    "AssetClass": "Networking",
                    "AssetService": "AWS Elastic Load Balancer",
                    "AssetComponent": "Classic Load Balancer"
                },
                "Resources": [
                    {
                        "Type": "AwsElbLoadBalancer",
                        "Id": clbArn,
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {
                            "AwsElbLoadBalancer": {
                                "DnsName": dnsName,
                                "Scheme": clbScheme,
                                "SecurityGroups": lbSgs,
                                "Subnets": lbSubnets,
                                "VpcId": lbVpc,
                                "AvailabilityZones": lbAzs,
                                "LoadBalancerName": clbName
                            }
                        }
                    }
                ],
                "Compliance": {
                    "Status": "FAILED",
                    "RelatedRequirements": [
                        "NIST CSF V1.1 ID.BE-5",
                        "NIST CSF V1.1 PR.DS-4",
                        "NIST CSF V1.1 PR.PT-5",
                        "NIST SP 800-53 Rev. 4 AU-4",
                        "NIST SP 800-53 Rev. 4 CP-2",
                        "NIST SP 800-53 Rev. 4 CP-7",
                        "NIST SP 800-53 Rev. 4 CP-8",
                        "NIST SP 800-53 Rev. 4 CP-11",
                        "NIST SP 800-53 Rev. 4 CP-13",
                        "NIST SP 800-53 Rev. 4 PL-8",
                        "NIST SP 800-53 Rev. 4 SA-14",
                        "NIST SP 800-53 Rev. 4 SC-5",
                        "NIST SP 800-53 Rev. 4 SC-6",
                        "AICPA TSC CC3.1",
                        "AICPA TSC A1.1",
                        "AICPA TSC A1.2",
                        "ISO 27001:2013 A.11.1.4",
                        "ISO 27001:2013 A.12.3.1",
                        "ISO 27001:2013 A.17.1.1",
                        "ISO 27001:2013 A.17.1.2",
                        "ISO 27001:2013 A.17.2.1"
                    ]
                },
                "Workflow": {"Status": "NEW"},
                "RecordState": "ACTIVE",
            }
            yield finding
        else:
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": clbArn + "/classic-loadbalancer-cross-zone-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": clbArn,
                "AwsAccountId": awsAccountId,
                "Types": ["Software and Configuration Checks/AWS Security Best Practices"],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": "INFORMATIONAL"},
                "Confidence": 99,
                "Title": "[ELB.3] Classic load balancers should have cross-zone load balancing configured",
                "Description": "Classic load balancer "
                + clbName
                + " has cross-zone load balancing configured.",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on cross-zone load balancing refer to the Configure Cross-Zone Load Balancing for Your Classic Load Balancer section of the Classic Load Balancers User Guide.",
                        "Url": "https://docs.aws.amazon.com/elasticloadbalancing/latest/classic/enable-disable-crosszone-lb.html",
                    }
                },
                "ProductFields": {
                    "ProductName": "ElectricEye",
                    "Provider": "AWS",
                    "ProviderType": "CSP",
                    "ProviderAccountId": awsAccountId,
                    "AssetRegion": awsRegion,
                    "AssetDetails": assetB64,
                    "AssetClass": "Networking",
                    "AssetService": "AWS Elastic Load Balancer",
                    "AssetComponent": "Classic Load Balancer"
                },
                "Resources": [
                    {
                        "Type": "AwsElbLoadBalancer",
                        "Id": clbArn,
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {
                            "AwsElbLoadBalancer": {
                                "DnsName": dnsName,
                                "Scheme": clbScheme,
                                "SecurityGroups": lbSgs,
                                "Subnets": lbSubnets,
                                "VpcId": lbVpc,
                                "AvailabilityZones": lbAzs,
                                "LoadBalancerName": clbName
                            }
                        }
                    }
                ],
                "Compliance": {
                    "Status": "PASSED",
                    "RelatedRequirements": [
                        "NIST CSF V1.1 ID.BE-5",
                        "NIST CSF V1.1 PR.DS-4",
                        "NIST CSF V1.1 PR.PT-5",
                        "NIST SP 800-53 Rev. 4 AU-4",
                        "NIST SP 800-53 Rev. 4 CP-2",
                        "NIST SP 800-53 Rev. 4 CP-7",
                        "NIST SP 800-53 Rev. 4 CP-8",
                        "NIST SP 800-53 Rev. 4 CP-11",
                        "NIST SP 800-53 Rev. 4 CP-13",
                        "NIST SP 800-53 Rev. 4 PL-8",
                        "NIST SP 800-53 Rev. 4 SA-14",
                        "NIST SP 800-53 Rev. 4 SC-5",
                        "NIST SP 800-53 Rev. 4 SC-6",
                        "AICPA TSC CC3.1",
                        "AICPA TSC A1.1",
                        "AICPA TSC A1.2",
                        "ISO 27001:2013 A.11.1.4",
                        "ISO 27001:2013 A.12.3.1",
                        "ISO 27001:2013 A.17.1.1",
                        "ISO 27001:2013 A.17.1.2",
                        "ISO 27001:2013 A.17.2.1"
                    ]
                },
                "Workflow": {"Status": "RESOLVED"},
                "RecordState": "ARCHIVED",
            }
            yield finding

@registry.register_check("elasticloadbalancing")
def clb_connection_draining_check(cache: dict, session, awsAccountId: str, awsRegion: str, awsPartition: str) -> dict:
    """[ELB.4] Classic load balancers should have connection draining configured"""
    elb = session.client("elb")
    # ISO Time
    iso8601Time = (datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat())
    for lb in describe_clbs(cache, session):
        # B64 encode all of the details for the Asset
        assetJson = json.dumps(lb,default=str).encode("utf-8")
        assetB64 = base64.b64encode(assetJson)
        clbName = lb["LoadBalancerName"]
        clbArn = f"arn:{awsPartition}:elasticloadbalancing:{awsRegion}:{awsAccountId}:loadbalancer/{clbName}"
        dnsName = lb["DNSName"]
        lbSgs = lb["SecurityGroups"]
        lbSubnets = lb["Subnets"]
        lbAzs = lb["AvailabilityZones"]
        lbVpc = lb["VPCId"]
        clbScheme = lb["Scheme"]
        # Get Attrs
        response = elb.describe_load_balancer_attributes(LoadBalancerName=clbName)
        connectionDrainCheck = str(
            response["LoadBalancerAttributes"]["ConnectionDraining"]["Enabled"]
        )
        if connectionDrainCheck == "False":
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": clbArn + "/classic-loadbalancer-connection-draining-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": clbArn,
                "AwsAccountId": awsAccountId,
                "Types": ["Software and Configuration Checks/AWS Security Best Practices"],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": "LOW"},
                "Confidence": 99,
                "Title": "[ELB.4] Classic load balancers should have connection draining configured",
                "Description": "Classic load balancer "
                + clbName
                + " does not have connection draining configured. Refer to the remediation instructions to remediate this behavior",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on connection draining refer to the Configure Connection Draining for Your Classic Load Balancer section of the Classic Load Balancers User Guide.",
                        "Url": "https://docs.aws.amazon.com/elasticloadbalancing/latest/classic/config-conn-drain.html",
                    }
                },
                "ProductFields": {
                    "ProductName": "ElectricEye",
                    "Provider": "AWS",
                    "ProviderType": "CSP",
                    "ProviderAccountId": awsAccountId,
                    "AssetRegion": awsRegion,
                    "AssetDetails": assetB64,
                    "AssetClass": "Networking",
                    "AssetService": "AWS Elastic Load Balancer",
                    "AssetComponent": "Classic Load Balancer"
                },
                "Resources": [
                    {
                        "Type": "AwsElbLoadBalancer",
                        "Id": clbArn,
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {
                            "AwsElbLoadBalancer": {
                                "DnsName": dnsName,
                                "Scheme": clbScheme,
                                "SecurityGroups": lbSgs,
                                "Subnets": lbSubnets,
                                "VpcId": lbVpc,
                                "AvailabilityZones": lbAzs,
                                "LoadBalancerName": clbName
                            }
                        }
                    }
                ],
                "Compliance": {
                    "Status": "FAILED",
                    "RelatedRequirements": [
                        "NIST CSF V1.1 ID.BE-5",
                        "NIST CSF V1.1 PR.DS-4",
                        "NIST CSF V1.1 PR.PT-5",
                        "NIST SP 800-53 Rev. 4 AU-4",
                        "NIST SP 800-53 Rev. 4 CP-2",
                        "NIST SP 800-53 Rev. 4 CP-7",
                        "NIST SP 800-53 Rev. 4 CP-8",
                        "NIST SP 800-53 Rev. 4 CP-11",
                        "NIST SP 800-53 Rev. 4 CP-13",
                        "NIST SP 800-53 Rev. 4 PL-8",
                        "NIST SP 800-53 Rev. 4 SA-14",
                        "NIST SP 800-53 Rev. 4 SC-5",
                        "NIST SP 800-53 Rev. 4 SC-6",
                        "AICPA TSC CC3.1",
                        "AICPA TSC A1.1",
                        "AICPA TSC A1.2",
                        "ISO 27001:2013 A.11.1.4",
                        "ISO 27001:2013 A.12.3.1",
                        "ISO 27001:2013 A.17.1.1",
                        "ISO 27001:2013 A.17.1.2",
                        "ISO 27001:2013 A.17.2.1"
                    ]
                },
                "Workflow": {"Status": "NEW"},
                "RecordState": "ACTIVE",
            }
            yield finding
        else:
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": clbArn + "/classic-loadbalancer-connection-draining-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": clbArn,
                "AwsAccountId": awsAccountId,
                "Types": ["Software and Configuration Checks/AWS Security Best Practices"],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": "INFORMATIONAL"},
                "Confidence": 99,
                "Title": "[ELB.4] Classic load balancers should have connection draining configured",
                "Description": "Classic load balancer "
                + clbName
                + " does not have connection draining configured.",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on connection draining refer to the Configure Connection Draining for Your Classic Load Balancer section of the Classic Load Balancers User Guide.",
                        "Url": "https://docs.aws.amazon.com/elasticloadbalancing/latest/classic/config-conn-drain.html",
                    }
                },
                "ProductFields": {
                    "ProductName": "ElectricEye",
                    "Provider": "AWS",
                    "ProviderType": "CSP",
                    "ProviderAccountId": awsAccountId,
                    "AssetRegion": awsRegion,
                    "AssetDetails": assetB64,
                    "AssetClass": "Networking",
                    "AssetService": "AWS Elastic Load Balancer",
                    "AssetComponent": "Classic Load Balancer"
                },
                "Resources": [
                    {
                        "Type": "AwsElbLoadBalancer",
                        "Id": clbArn,
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {
                            "AwsElbLoadBalancer": {
                                "DnsName": dnsName,
                                "Scheme": clbScheme,
                                "SecurityGroups": lbSgs,
                                "Subnets": lbSubnets,
                                "VpcId": lbVpc,
                                "AvailabilityZones": lbAzs,
                                "LoadBalancerName": clbName
                            }
                        }
                    }
                ],
                "Compliance": {
                    "Status": "PASSED",
                    "RelatedRequirements": [
                        "NIST CSF V1.1 ID.BE-5",
                        "NIST CSF V1.1 PR.DS-4",
                        "NIST CSF V1.1 PR.PT-5",
                        "NIST SP 800-53 Rev. 4 AU-4",
                        "NIST SP 800-53 Rev. 4 CP-2",
                        "NIST SP 800-53 Rev. 4 CP-7",
                        "NIST SP 800-53 Rev. 4 CP-8",
                        "NIST SP 800-53 Rev. 4 CP-11",
                        "NIST SP 800-53 Rev. 4 CP-13",
                        "NIST SP 800-53 Rev. 4 PL-8",
                        "NIST SP 800-53 Rev. 4 SA-14",
                        "NIST SP 800-53 Rev. 4 SC-5",
                        "NIST SP 800-53 Rev. 4 SC-6",
                        "AICPA TSC CC3.1",
                        "AICPA TSC A1.1",
                        "AICPA TSC A1.2",
                        "ISO 27001:2013 A.11.1.4",
                        "ISO 27001:2013 A.12.3.1",
                        "ISO 27001:2013 A.17.1.1",
                        "ISO 27001:2013 A.17.1.2",
                        "ISO 27001:2013 A.17.2.1"
                    ]
                },
                "Workflow": {"Status": "RESOLVED"},
                "RecordState": "ARCHIVED",
            }
            yield finding

@registry.register_check("elasticloadbalancing")
def clb_access_logging_check(cache: dict, session, awsAccountId: str, awsRegion: str, awsPartition: str) -> dict:
    """[ELB.5] Classic load balancers should enable access logging"""
    elb = session.client("elb")
    # ISO Time
    iso8601Time = (datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat())
    for lb in describe_clbs(cache, session):
        # B64 encode all of the details for the Asset
        assetJson = json.dumps(lb,default=str).encode("utf-8")
        assetB64 = base64.b64encode(assetJson)
        clbName = lb["LoadBalancerName"]
        clbArn = f"arn:{awsPartition}:elasticloadbalancing:{awsRegion}:{awsAccountId}:loadbalancer/{clbName}"
        dnsName = lb["DNSName"]
        lbSgs = lb["SecurityGroups"]
        lbSubnets = lb["Subnets"]
        lbAzs = lb["AvailabilityZones"]
        lbVpc = lb["VPCId"]
        clbScheme = lb["Scheme"]
        # Get Attrs
        if elb.describe_load_balancer_attributes(LoadBalancerName=clbName)["LoadBalancerAttributes"]["AccessLog"]["Enabled"] is False:
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": clbArn + "/classic-loadbalancer-access-logging-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": clbArn,
                "AwsAccountId": awsAccountId,
                "Types": ["Software and Configuration Checks/AWS Security Best Practices"],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": "MEDIUM"},
                "Confidence": 99,
                "Title": "[ELB.5] Classic load balancers should enable access logging",
                "Description": "Classic load balancer "
                + clbName
                + " does not have access logging enabled. Refer to the remediation instructions to remediate this behavior",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on access logging refer to the Access Logs for Your Classic Load Balancer section of the Classic Load Balancers User Guide.",
                        "Url": "https://docs.aws.amazon.com/elasticloadbalancing/latest/classic/access-log-collection.html",
                    }
                },
                "ProductFields": {
                    "ProductName": "ElectricEye",
                    "Provider": "AWS",
                    "ProviderType": "CSP",
                    "ProviderAccountId": awsAccountId,
                    "AssetRegion": awsRegion,
                    "AssetDetails": assetB64,
                    "AssetClass": "Networking",
                    "AssetService": "AWS Elastic Load Balancer",
                    "AssetComponent": "Classic Load Balancer"
                },
                "Resources": [
                    {
                        "Type": "AwsElbLoadBalancer",
                        "Id": clbArn,
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {
                            "AwsElbLoadBalancer": {
                                "DnsName": dnsName,
                                "Scheme": clbScheme,
                                "SecurityGroups": lbSgs,
                                "Subnets": lbSubnets,
                                "VpcId": lbVpc,
                                "AvailabilityZones": lbAzs,
                                "LoadBalancerName": clbName
                            }
                        }
                    }
                ],
                "Compliance": {
                    "Status": "FAILED",
                    "RelatedRequirements": [
                        "NIST CSF V1.1 ID.AM-3",
                        "NIST CSF V1.1 DE.AE-1",
                        "NIST CSF V1.1 DE.AE-3",
                        "NIST CSF V1.1 DE.CM-1",
                        "NIST CSF V1.1 DE.CM-7",
                        "NIST CSF V1.1 PR.PT-1",
                        "NIST SP 800-53 Rev. 4 AC-2",
                        "NIST SP 800-53 Rev. 4 AC-4",
                        "NIST SP 800-53 Rev. 4 AU-6",
                        "NIST SP 800-53 Rev. 4 AU-12",
                        "NIST SP 800-53 Rev. 4 CA-3",
                        "NIST SP 800-53 Rev. 4 CA-7",
                        "NIST SP 800-53 Rev. 4 CA-9",
                        "NIST SP 800-53 Rev. 4 CM-2",
                        "NIST SP 800-53 Rev. 4 CM-3",
                        "NIST SP 800-53 Rev. 4 CM-8",
                        "NIST SP 800-53 Rev. 4 IR-4",
                        "NIST SP 800-53 Rev. 4 IR-5",
                        "NIST SP 800-53 Rev. 4 IR-8",
                        "NIST SP 800-53 Rev. 4 PE-3",
                        "NIST SP 800-53 Rev. 4 PE-6",
                        "NIST SP 800-53 Rev. 4 PE-20",
                        "NIST SP 800-53 Rev. 4 PL-8",
                        "NIST SP 800-53 Rev. 4 SC-5",
                        "NIST SP 800-53 Rev. 4 SC-7",
                        "NIST SP 800-53 Rev. 4 SI-4",
                        "AICPA TSC CC3.2",
                        "AICPA TSC CC6.1",
                        "AICPA TSC CC7.2",
                        "ISO 27001:2013 A.12.1.1",
                        "ISO 27001:2013 A.12.1.2",
                        "ISO 27001:2013 A.12.4.1",
                        "ISO 27001:2013 A.12.4.2",
                        "ISO 27001:2013 A.12.4.3",
                        "ISO 27001:2013 A.12.4.4",
                        "ISO 27001:2013 A.12.7.1",
                        "ISO 27001:2013 A.13.1.1",
                        "ISO 27001:2013 A.13.2.1",
                        "ISO 27001:2013 A.13.2.2",
                        "ISO 27001:2013 A.14.2.7",
                        "ISO 27001:2013 A.15.2.1",
                        "ISO 27001:2013 A.16.1.7"
                    ]
                },
                "Workflow": {"Status": "NEW"},
                "RecordState": "ACTIVE"
            }
            yield finding
        else:
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": clbArn + "/classic-loadbalancer-access-logging-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": clbArn,
                "AwsAccountId": awsAccountId,
                "Types": ["Software and Configuration Checks/AWS Security Best Practices"],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": "INFORMATIONAL"},
                "Confidence": 99,
                "Title": "[ELB.5] Classic load balancers should enable access logging",
                "Description": "Classic load balancer "
                + clbName
                + " does not have access logging enabled.",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on access logging refer to the Access Logs for Your Classic Load Balancer section of the Classic Load Balancers User Guide.",
                        "Url": "https://docs.aws.amazon.com/elasticloadbalancing/latest/classic/access-log-collection.html",
                    }
                },
                "ProductFields": {
                    "ProductName": "ElectricEye",
                    "Provider": "AWS",
                    "ProviderType": "CSP",
                    "ProviderAccountId": awsAccountId,
                    "AssetRegion": awsRegion,
                    "AssetDetails": assetB64,
                    "AssetClass": "Networking",
                    "AssetService": "AWS Elastic Load Balancer",
                    "AssetComponent": "Classic Load Balancer"
                },
                "Resources": [
                    {
                        "Type": "AwsElbLoadBalancer",
                        "Id": clbArn,
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {
                            "AwsElbLoadBalancer": {
                                "DnsName": dnsName,
                                "Scheme": clbScheme,
                                "SecurityGroups": lbSgs,
                                "Subnets": lbSubnets,
                                "VpcId": lbVpc,
                                "AvailabilityZones": lbAzs,
                                "LoadBalancerName": clbName
                            }
                        }
                    }
                ],
                "Compliance": {
                    "Status": "PASSED",
                    "RelatedRequirements": [
                        "NIST CSF V1.1 ID.AM-3",
                        "NIST CSF V1.1 DE.AE-1",
                        "NIST CSF V1.1 DE.AE-3",
                        "NIST CSF V1.1 DE.CM-1",
                        "NIST CSF V1.1 DE.CM-7",
                        "NIST CSF V1.1 PR.PT-1",
                        "NIST SP 800-53 Rev. 4 AC-2",
                        "NIST SP 800-53 Rev. 4 AC-4",
                        "NIST SP 800-53 Rev. 4 AU-6",
                        "NIST SP 800-53 Rev. 4 AU-12",
                        "NIST SP 800-53 Rev. 4 CA-3",
                        "NIST SP 800-53 Rev. 4 CA-7",
                        "NIST SP 800-53 Rev. 4 CA-9",
                        "NIST SP 800-53 Rev. 4 CM-2",
                        "NIST SP 800-53 Rev. 4 CM-3",
                        "NIST SP 800-53 Rev. 4 CM-8",
                        "NIST SP 800-53 Rev. 4 IR-4",
                        "NIST SP 800-53 Rev. 4 IR-5",
                        "NIST SP 800-53 Rev. 4 IR-8",
                        "NIST SP 800-53 Rev. 4 PE-3",
                        "NIST SP 800-53 Rev. 4 PE-6",
                        "NIST SP 800-53 Rev. 4 PE-20",
                        "NIST SP 800-53 Rev. 4 PL-8",
                        "NIST SP 800-53 Rev. 4 SC-5",
                        "NIST SP 800-53 Rev. 4 SC-7",
                        "NIST SP 800-53 Rev. 4 SI-4",
                        "AICPA TSC CC3.2",
                        "AICPA TSC CC6.1",
                        "AICPA TSC CC7.2",
                        "ISO 27001:2013 A.12.1.1",
                        "ISO 27001:2013 A.12.1.2",
                        "ISO 27001:2013 A.12.4.1",
                        "ISO 27001:2013 A.12.4.2",
                        "ISO 27001:2013 A.12.4.3",
                        "ISO 27001:2013 A.12.4.4",
                        "ISO 27001:2013 A.12.7.1",
                        "ISO 27001:2013 A.13.1.1",
                        "ISO 27001:2013 A.13.2.1",
                        "ISO 27001:2013 A.13.2.2",
                        "ISO 27001:2013 A.14.2.7",
                        "ISO 27001:2013 A.15.2.1",
                        "ISO 27001:2013 A.16.1.7"
                    ]
                },
                "Workflow": {"Status": "RESOLVED"},
                "RecordState": "ARCHIVED"
            }
            yield finding

@registry.register_check("elasticloadbalancing")
def public_clb_shodan_check(cache: dict, session, awsAccountId: str, awsRegion: str, awsPartition: str) -> dict:
    """[ELB.6] Internet-facing Classic Load Balancers should be monitored for being indexed by Shodan"""
    shodanApiKey = get_shodan_api_key(cache)
    # ISO Time
    iso8601time = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()        
    for lb in describe_clbs(cache, session):
        if shodanApiKey is None:
            continue
        # B64 encode all of the details for the Asset
        assetJson = json.dumps(lb,default=str).encode("utf-8")
        assetB64 = base64.b64encode(assetJson)
        clbName = lb["LoadBalancerName"]
        clbArn = f"arn:{awsPartition}:elasticloadbalancing:{awsRegion}:{awsAccountId}:loadbalancer/{clbName}"
        dnsName = lb["DNSName"]
        lbSgs = lb["SecurityGroups"]
        lbSubnets = lb["Subnets"]
        lbAzs = lb["AvailabilityZones"]
        lbVpc = lb["VPCId"]
        clbScheme = lb["Scheme"]
        if clbScheme == "internet-facing":
            # Use Google DNS to resolve
            clbIp = google_dns_resolver(dnsName)
            if clbIp is None:
                continue
            # check if IP indexed by Shodan
            r = safe_requests.get(url=f"{SHODAN_HOSTS_URL}{clbIp}?key={shodanApiKey}").json()
            if str(r) == "{'error': 'No information available for that IP.'}":
                # this is a passing check
                finding = {
                    "SchemaVersion": "2018-10-08",
                    "Id": f"{clbArn}/{dnsName}/classic-load-balancer-shodan-index-check",
                    "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                    "GeneratorId": f"{clbArn}/{dnsName}/classic-load-balancer-shodan-index-check",
                    "AwsAccountId": awsAccountId,
                    "Types": ["Effects/Data Exposure"],
                    "CreatedAt": iso8601time,
                    "UpdatedAt": iso8601time,
                    "Severity": {"Label": "INFORMATIONAL"},
                    "Title": "[ELB.6] Internet-facing Classic Load Balancers should be monitored for being indexed by Shodan",
                    "Description": f"Classic Load Balancer {clbName} has not been indexed by Shodan.",
                    "Remediation": {
                        "Recommendation": {
                            "Text": "To learn more about the information that Shodan indexed on your host refer to the URL in the remediation section.",
                            "Url": SHODAN_HOSTS_URL
                        }
                    },
                    "ProductFields": {
                        "ProductName": "ElectricEye",
                        "Provider": "AWS",
                        "ProviderType": "CSP",
                        "ProviderAccountId": awsAccountId,
                        "AssetRegion": awsRegion,
                        "AssetDetails": assetB64,
                        "AssetClass": "Networking",
                        "AssetService": "AWS Elastic Load Balancer",
                        "AssetComponent": "Classic Load Balancer"
                    },
                    "Resources": [
                        {
                            "Type": "AwsElbLoadBalancer",
                            "Id": clbArn,
                            "Partition": awsPartition,
                            "Region": awsRegion,
                            "Details": {
                                "AwsElbLoadBalancer": {
                                    "DnsName": dnsName,
                                    "Scheme": clbScheme,
                                    "SecurityGroups": lbSgs,
                                    "Subnets": lbSubnets,
                                    "VpcId": lbVpc,
                                    "AvailabilityZones": lbAzs,
                                    "LoadBalancerName": clbName
                                }
                            }
                        }
                    ],
                    "Compliance": {
                        "Status": "PASSED",
                        "RelatedRequirements": [
                            "NIST CSF V1.1 ID.RA-2",
                            "NIST CSF V1.1 DE.AE-2",
                            "NIST SP 800-53 Rev. 4 AU-6",
                            "NIST SP 800-53 Rev. 4 CA-7",
                            "NIST SP 800-53 Rev. 4 IR-4",
                            "NIST SP 800-53 Rev. 4 PM-15",
                            "NIST SP 800-53 Rev. 4 PM-16",
                            "NIST SP 800-53 Rev. 4 SI-4",
                            "NIST SP 800-53 Rev. 4 SI-5",
                            "AIPCA TSC CC3.2",
                            "AIPCA TSC CC7.2",
                            "ISO 27001:2013 A.6.1.4",
                            "ISO 27001:2013 A.12.4.1",
                            "ISO 27001:2013 A.16.1.1",
                            "ISO 27001:2013 A.16.1.4",
                            "MITRE ATT&CK T1040",
                            "MITRE ATT&CK T1046",
                            "MITRE ATT&CK T1580",
                            "MITRE ATT&CK T1590",
                            "MITRE ATT&CK T1592",
                            "MITRE ATT&CK T1595"
                        ]
                    },
                    "Workflow": {"Status": "RESOLVED"},
                    "RecordState": "ARCHIVED"
                }
                yield finding
            else:
                assetPayload = {
                    "LoadBalancer": lb,
                    "Shodan": r
                }
                assetJson = json.dumps(assetPayload,default=str).encode("utf-8")
                assetB64 = base64.b64encode(assetJson)
                finding = {
                    "SchemaVersion": "2018-10-08",
                    "Id": f"{clbArn}/{dnsName}/classic-load-balancer-shodan-index-check",
                    "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                    "GeneratorId": f"{clbArn}/{dnsName}/classic-load-balancer-shodan-index-check",
                    "AwsAccountId": awsAccountId,
                    "Types": ["Effects/Data Exposure"],
                    "CreatedAt": iso8601time,
                    "UpdatedAt": iso8601time,
                    "Severity": {"Label": "MEDIUM"},
                    "Title": "[ELB.6] Internet-facing Classic Load Balancers should be monitored for being indexed by Shodan",
                    "Description": f"Classic Load Balancer {clbName} has been indexed by Shodan on IP address {clbIp} - resolved from DNS name {dnsName}. Shodan is an 'internet search engine' which continuously crawls and scans across the entire internet to capture host, geolocation, TLS, and running service information. Shodan is a popular tool used by blue teams, security researchers and adversaries alike. Having your asset indexed on Shodan, depending on its configuration, may increase its risk of unauthorized access and further compromise. Review your configuration and refer to the Shodan URL in the remediation section to take action to reduce your exposure and harden your host.",
                    "Remediation": {
                        "Recommendation": {
                            "Text": "To learn more about the information that Shodan indexed on your host refer to the URL in the remediation section.",
                            "Url": f"{SHODAN_HOSTS_URL}{clbIp}"
                        }
                    },
                    "ProductFields": {
                        "ProductName": "ElectricEye",
                        "Provider": "AWS",
                        "ProviderType": "CSP",
                        "ProviderAccountId": awsAccountId,
                        "AssetRegion": awsRegion,
                        "AssetDetails": assetB64,
                        "AssetClass": "Networking",
                        "AssetService": "AWS Elastic Load Balancer",
                        "AssetComponent": "Classic Load Balancer"
                    },
                    "Resources": [
                        {
                            "Type": "AwsElbLoadBalancer",
                            "Id": clbArn,
                            "Partition": awsPartition,
                            "Region": awsRegion,
                            "Details": {
                                "AwsElbLoadBalancer": {
                                    "DnsName": dnsName,
                                    "Scheme": clbScheme,
                                    "SecurityGroups": lbSgs,
                                    "Subnets": lbSubnets,
                                    "VpcId": lbVpc,
                                    "AvailabilityZones": lbAzs,
                                    "LoadBalancerName": clbName
                                }
                            }
                        }
                    ],
                    "Compliance": {
                        "Status": "FAILED",
                        "RelatedRequirements": [
                            "NIST CSF V1.1 ID.RA-2",
                            "NIST CSF V1.1 DE.AE-2",
                            "NIST SP 800-53 Rev. 4 AU-6",
                            "NIST SP 800-53 Rev. 4 CA-7",
                            "NIST SP 800-53 Rev. 4 IR-4",
                            "NIST SP 800-53 Rev. 4 PM-15",
                            "NIST SP 800-53 Rev. 4 PM-16",
                            "NIST SP 800-53 Rev. 4 SI-4",
                            "NIST SP 800-53 Rev. 4 SI-5",
                            "AIPCA TSC CC3.2",
                            "AIPCA TSC CC7.2",
                            "ISO 27001:2013 A.6.1.4",
                            "ISO 27001:2013 A.12.4.1",
                            "ISO 27001:2013 A.16.1.1",
                            "ISO 27001:2013 A.16.1.4",
                            "MITRE ATT&CK T1040",
                            "MITRE ATT&CK T1046",
                            "MITRE ATT&CK T1580",
                            "MITRE ATT&CK T1590",
                            "MITRE ATT&CK T1592",
                            "MITRE ATT&CK T1595"
                        ]
                    },
                    "Workflow": {"Status": "NEW"},
                    "RecordState": "ACTIVE"
                }
                yield finding

## END ??
