# This file is part of ElectricEye.

# ElectricEye is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# ElectricEye is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along with ElectricEye.  
# If not, see https://github.com/jonrau1/ElectricEye/blob/master/LICENSE.

import boto3
import uuid
import os
import datetime
from auditors.Auditor import Auditor
# import boto3 clients
sts = boto3.client('sts')
accessanalyzer = boto3.client('accessanalyzer')
guardduty = boto3.client('guardduty')
detective = boto3.client('detective')
# create env vars
awsRegion = os.environ['AWS_REGION']
awsAccountId = sts.get_caller_identity()['Account']

class iamAccessAnalyzerDetectorCheck(Auditor):
    def execute(self):
        response = accessanalyzer.list_analyzers()
        iamAccessAnalyzerCheck = str(response['analyzers'])
        # ISO Time
        iso8601Time = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()
        # unique ID
        generatorUuid = str(uuid.uuid4())
        if iamAccessAnalyzerCheck == '[]':
            finding = {
                'SchemaVersion': '2018-10-08',
                'Id': awsAccountId + '/security-services-iaa-enabled-check',
                'ProductArn': 'arn:aws:securityhub:' + awsRegion + ':' + awsAccountId + ':product/' + awsAccountId + '/default',
                'GeneratorId': generatorUuid,
                'AwsAccountId': awsAccountId,
                'Types': [ 'Software and Configuration Checks/AWS Security Best Practices' ],
                'FirstObservedAt': iso8601Time,
                'CreatedAt': iso8601Time,
                'UpdatedAt': iso8601Time,
                'Severity': { 'Label': 'MEDIUM' },
                'Confidence': 99,
                'Title': '[SecSvcs.1] Amazon IAM Access Analyzer should be enabled',
                'Description': 'Amazon IAM Access Analyzer is not enabled. Refer to the remediation instructions if this configuration is not intended',
                'Remediation': {
                    'Recommendation': {
                        'Text': 'If IAM Access Analyzer should be enabled refer to the Enabling Access Analyzer section of the AWS Identity and Access Management User Guide',
                        'Url': 'https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-getting-started.html#access-analyzer-enabling'
                    }
                },
                'ProductFields': {
                    'Product Name': 'ElectricEye'
                },
                'Resources': [
                    {
                        'Type': 'AwsAccount',
                        'Id': 'AWS::::Account:' + awsAccountId,
                        'Partition': 'aws',
                        'Region': awsRegion
                    }
                ],
                'Compliance': { 
                    'Status': 'FAILED',
                    'RelatedRequirements': [
                        'NIST CSF DE.AE-2',
                        'NIST SP 800-53 AU-6',
                        'NIST SP 800-53 CA-7',
                        'NIST SP 800-53 IR-4',
                        'NIST SP 800-53 SI-4',
                        'AICPA TSC 7.2',
                        'ISO 27001:2013 A.12.4.1',
                        'ISO 27001:2013 A.16.1.1',
                        'ISO 27001:2013 A.16.1.4'
                    ]
                },
                'Workflow': {
                    'Status': 'NEW'
                },
                'RecordState': 'ACTIVE'
            }
            yield finding
        else:
            finding = {
                'SchemaVersion': '2018-10-08',
                'Id': awsAccountId + '/security-services-iaa-enabled-check',
                'ProductArn': 'arn:aws:securityhub:' + awsRegion + ':' + awsAccountId + ':product/' + awsAccountId + '/default',
                'GeneratorId': generatorUuid,
                'AwsAccountId': awsAccountId,
                'Types': [ 'Software and Configuration Checks/AWS Security Best Practices' ],
                'FirstObservedAt': iso8601Time,
                'CreatedAt': iso8601Time,
                'UpdatedAt': iso8601Time,
                'Severity': { 'Label': 'INFORMATIONAL' },
                'Confidence': 99,
                'Title': '[SecSvcs.1] Amazon IAM Access Analyzer should be enabled',
                'Description': 'Amazon IAM Access Analyzer is enabled.',
                'Remediation': {
                    'Recommendation': {
                        'Text': 'If IAM Access Analyzer should be enabled refer to the Enabling Access Analyzer section of the AWS Identity and Access Management User Guide',
                        'Url': 'https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-getting-started.html#access-analyzer-enabling'
                    }
                },
                'ProductFields': {
                    'Product Name': 'ElectricEye'
                },
                'Resources': [
                    {
                        'Type': 'AwsAccount',
                        'Id': 'AWS::::Account:' + awsAccountId,
                        'Partition': 'aws',
                        'Region': awsRegion
                    }
                ],
                'Compliance': { 
                    'Status': 'PASSED',
                    'RelatedRequirements': [
                        'NIST CSF DE.AE-2',
                        'NIST SP 800-53 AU-6',
                        'NIST SP 800-53 CA-7',
                        'NIST SP 800-53 IR-4',
                        'NIST SP 800-53 SI-4',
                        'AICPA TSC 7.2',
                        'ISO 27001:2013 A.12.4.1',
                        'ISO 27001:2013 A.16.1.1',
                        'ISO 27001:2013 A.16.1.4'
                    ]
                },
                'Workflow': {
                    'Status': 'RESOLVED'
                },
                'RecordState': 'ARCHIVED'
            }
            yield finding

class GuardDutyDetectorCheck(Auditor):
    def execute(self):
        response = guardduty.list_detectors()
        guarddutyDetectorCheck = str(response['DetectorIds'])
        # ISO Time
        iso8601Time = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()
        # unique ID
        generatorUuid = str(uuid.uuid4())
        if guarddutyDetectorCheck == '[]':
            finding = {
                'SchemaVersion': '2018-10-08',
                'Id': awsAccountId + '/security-services-guardduty-enabled-check',
                'ProductArn': 'arn:aws:securityhub:' + awsRegion + ':' + awsAccountId + ':product/' + awsAccountId + '/default',
                'GeneratorId': generatorUuid,
                'AwsAccountId': awsAccountId,
                'Types': [ 'Software and Configuration Checks/AWS Security Best Practices' ],
                'FirstObservedAt': iso8601Time,
                'CreatedAt': iso8601Time,
                'UpdatedAt': iso8601Time,
                'Severity': { 'Label': 'MEDIUM' },
                'Confidence': 99,
                'Title': '[SecSvcs.2] Amazon GuardDuty should be enabled',
                'Description': 'Amazon GuardDuty is not enabled. Refer to the remediation instructions if this configuration is not intended',
                'Remediation': {
                    'Recommendation': {
                        'Text': 'If GuardDuty should be enabled refer to the Setting Up GuardDuty section of the Amazon GuardDuty User Guide',
                        'Url': 'https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_settingup.html'
                    }
                },
                'ProductFields': {
                    'Product Name': 'ElectricEye'
                },
                'Resources': [
                    {
                        'Type': 'AwsAccount',
                        'Id': 'AWS::::Account:' + awsAccountId,
                        'Partition': 'aws',
                        'Region': awsRegion
                    }
                ],
                'Compliance': { 
                    'Status': 'FAILED',
                    'RelatedRequirements': [
                        'NIST CSF DE.AE-2',
                        'NIST SP 800-53 AU-6',
                        'NIST SP 800-53 CA-7',
                        'NIST SP 800-53 IR-4',
                        'NIST SP 800-53 SI-4',
                        'AICPA TSC 7.2',
                        'ISO 27001:2013 A.12.4.1',
                        'ISO 27001:2013 A.16.1.1',
                        'ISO 27001:2013 A.16.1.4'
                    ]
                },
                'Workflow': {
                    'Status': 'NEW'
                },
                'RecordState': 'ACTIVE'
            }
            yield finding
        else:
            finding = {
                'SchemaVersion': '2018-10-08',
                'Id': awsAccountId + '/security-services-guardduty-enabled-check',
                'ProductArn': 'arn:aws:securityhub:' + awsRegion + ':' + awsAccountId + ':product/' + awsAccountId + '/default',
                'GeneratorId': generatorUuid,
                'AwsAccountId': awsAccountId,
                'Types': [ 'Software and Configuration Checks/AWS Security Best Practices' ],
                'FirstObservedAt': iso8601Time,
                'CreatedAt': iso8601Time,
                'UpdatedAt': iso8601Time,
                'Severity': { 'Label': 'INFORMATIONAL' },
                'Confidence': 99,
                'Title': '[SecSvcs.2] Amazon GuardDuty should be enabled',
                'Description': 'Amazon GuardDuty is not enabled. Refer to the remediation instructions if this configuration is not intended',
                'Remediation': {
                    'Recommendation': {
                        'Text': 'If GuardDuty should be enabled refer to the Setting Up GuardDuty section of the Amazon GuardDuty User Guide',
                        'Url': 'https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_settingup.html'
                    }
                },
                'ProductFields': {
                    'Product Name': 'ElectricEye'
                },
                'Resources': [
                    {
                        'Type': 'AwsAccount',
                        'Id': 'AWS::::Account:' + awsAccountId,
                        'Partition': 'aws',
                        'Region': awsRegion
                    }
                ],
                'Compliance': { 
                    'Status': 'PASSED',
                    'RelatedRequirements': [
                        'NIST CSF DE.AE-2',
                        'NIST SP 800-53 AU-6',
                        'NIST SP 800-53 CA-7',
                        'NIST SP 800-53 IR-4',
                        'NIST SP 800-53 SI-4',
                        'AICPA TSC 7.2',
                        'ISO 27001:2013 A.12.4.1',
                        'ISO 27001:2013 A.16.1.1',
                        'ISO 27001:2013 A.16.1.4'
                    ]
                },
                'Workflow': {
                    'Status': 'RESOLVED'
                },
                'RecordState': 'ARCHIVED'
            }
            yield finding

class DetectiveGraphCheck(Auditor):
    def execute(self):
        try:
            response = detective.list_graphs(MaxResults=200)
            # ISO Time
            iso8601Time = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()
            # unique ID
            generatorUuid = str(uuid.uuid4())
            if str(response['GraphList']) == '[]':
                finding = {
                    'SchemaVersion': '2018-10-08',
                    'Id': awsAccountId + '/security-services-detective-enabled-check',
                    'ProductArn': 'arn:aws:securityhub:' + awsRegion + ':' + awsAccountId + ':product/' + awsAccountId + '/default',
                    'GeneratorId': generatorUuid,
                    'AwsAccountId': awsAccountId,
                    'Types': [ 'Software and Configuration Checks/AWS Security Best Practices' ],
                    'FirstObservedAt': iso8601Time,
                    'CreatedAt': iso8601Time,
                    'UpdatedAt': iso8601Time,
                    'Severity': { 'Label': 'MEDIUM' },
                    'Confidence': 99,
                    'Title': '[SecSvcs.3] Amazon Detective should be enabled',
                    'Description': 'Amazon Detective is not enabled. Refer to the remediation instructions if this configuration is not intended',
                    'Remediation': {
                        'Recommendation': {
                            'Text': 'If Detective should be enabled refer to the Setting up Amazon Detective section of the Amazon Detective Administration Guide',
                            'Url': 'https://docs.aws.amazon.com/detective/latest/adminguide/detective-setup.html'
                        }
                    },
                    'ProductFields': {
                        'Product Name': 'ElectricEye'
                    },
                    'Resources': [
                        {
                            'Type': 'AwsAccount',
                            'Id': 'AWS::::Account:' + awsAccountId,
                            'Partition': 'aws',
                            'Region': awsRegion
                        }
                    ],
                    'Compliance': { 
                        'Status': 'FAILED',
                        'RelatedRequirements': [
                            'NIST CSF DE.AE-2',
                            'NIST SP 800-53 AU-6',
                            'NIST SP 800-53 CA-7',
                            'NIST SP 800-53 IR-4',
                            'NIST SP 800-53 SI-4',
                            'AICPA TSC 7.2',
                            'ISO 27001:2013 A.12.4.1',
                            'ISO 27001:2013 A.16.1.1',
                            'ISO 27001:2013 A.16.1.4'
                        ]
                    },
                    'Workflow': {
                        'Status': 'NEW'
                    },
                    'RecordState': 'ACTIVE'
                }
                yield finding
            else:
                finding = {
                    'SchemaVersion': '2018-10-08',
                    'Id': awsAccountId + '/security-services-detective-enabled-check',
                    'ProductArn': 'arn:aws:securityhub:' + awsRegion + ':' + awsAccountId + ':product/' + awsAccountId + '/default',
                    'GeneratorId': generatorUuid,
                    'AwsAccountId': awsAccountId,
                    'Types': [ 'Software and Configuration Checks/AWS Security Best Practices' ],
                    'FirstObservedAt': iso8601Time,
                    'CreatedAt': iso8601Time,
                    'UpdatedAt': iso8601Time,
                    'Severity': { 'Label': 'INFORMATIONAL' },
                    'Confidence': 99,
                    'Title': '[SecSvcs.3] Amazon Detective should be enabled',
                    'Description': 'Amazon Detective is enabled.',
                    'Remediation': {
                        'Recommendation': {
                            'Text': 'If Detective should be enabled refer to the Setting up Amazon Detective section of the Amazon Detective Administration Guide',
                            'Url': 'https://docs.aws.amazon.com/detective/latest/adminguide/detective-setup.html'
                        }
                    },
                    'ProductFields': {
                        'Product Name': 'ElectricEye'
                    },
                    'Resources': [
                        {
                            'Type': 'AwsAccount',
                            'Id': 'AWS::::Account:' + awsAccountId,
                            'Partition': 'aws',
                            'Region': awsRegion
                        }
                    ],
                    'Compliance': { 
                        'Status': 'PASSED',
                        'RelatedRequirements': [
                            'NIST CSF DE.AE-2',
                            'NIST SP 800-53 AU-6',
                            'NIST SP 800-53 CA-7',
                            'NIST SP 800-53 IR-4',
                            'NIST SP 800-53 SI-4',
                            'AICPA TSC 7.2',
                            'ISO 27001:2013 A.12.4.1',
                            'ISO 27001:2013 A.16.1.1',
                            'ISO 27001:2013 A.16.1.4'
                        ]
                    },
                    'Workflow': {
                        'Status': 'RESOLVED'
                    },
                    'RecordState': 'ARCHIVED'
                }
                yield finding
        except Exception as e:
            print(e)
