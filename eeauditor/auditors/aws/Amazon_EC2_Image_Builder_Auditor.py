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
import datetime
import json
from check_register import CheckRegister

registry = CheckRegister()

imagebuilder = boto3.client("imagebuilder")


@registry.register_check("imagebuilder")
def imagebuilder_pipeline_tests_enabled_check(cache: dict, awsAccountId: str, awsRegion: str, awsPartition: str) -> dict:
    pipelines = imagebuilder.list_image_pipelines()
    pipeline_list = pipelines["imagePipelineList"]
    iso8601Time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for arn in pipeline_list:
        pipeline_arn = arn["arn"]
        pipeline_name = arn["name"]
        image_pipelines = imagebuilder.get_image_pipeline(imagePipelineArn=pipeline_arn)
        image_test_config = image_pipelines["imagePipeline"]["imageTestsConfiguration"]
        image_test_enabled = image_test_config["imageTestsEnabled"]
        if image_test_enabled == True:
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": pipeline_arn + "/imagebuilder-pipeline-tests-enabled-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": pipeline_arn,
                "AwsAccountId": awsAccountId,
                "Types": [
                    "Software and Configuration Checks/AWS Security Best Practices",
                    "Effects/Data Exposure",
                ],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": "INFORMATIONAL"},
                "Confidence": 99,
                "Title": "[ImageBuilder.1] Image pipeline tests should be enabled",
                "Description": "Image pipeline " + pipeline_name + " has tests enabled.",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on EC2 Image Builder Security and enabling image testing refer to the Best Practices section of the Amazon EC2 Image Builder Developer Guide.",
                        "Url": "https://docs.aws.amazon.com/imagebuilder/latest/userguide/security-best-practices.html",
                    }
                },
                "ProductFields": {"Product Name": "ElectricEye"},
                "Resources": [
                    {
                        "Type": "AwsImageBuilderPipeline",
                        "Id": pipeline_arn,
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {"AwsImageBuilderPipeline": {"PipelineName": pipeline_name}},
                    }
                ],
                "Compliance": {
                    "Status": "PASSED"
                },
                "Workflow": {"Status": "RESOLVED"},
                "RecordState": "ARCHIVED",
            }
            yield finding
        else:
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": pipeline_arn + "/imagebuilder-pipeline-tests-enabled-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": pipeline_arn,
                "AwsAccountId": awsAccountId,
                "Types": [
                    "Software and Configuration Checks/AWS Security Best Practices",
                    "Effects/Data Exposure",
                ],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": "MEDIUM"},
                "Confidence": 99,
                "Title": "[ImageBuilder.1] Image pipeline tests should be enabled",
                "Description": "Image pipeline " + pipeline_name + " does not have tests enabled.",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on EC2 Image Builder Security and enabling image testing refer to the Best Practices section of the Amazon EC2 Image Builder Developer Guide.",
                        "Url": "https://docs.aws.amazon.com/imagebuilder/latest/userguide/security-best-practices.html",
                    }
                },
                "ProductFields": {"Product Name": "ElectricEye"},
                "Resources": [
                    {
                        "Type": "AwsImageBuilderPipeline",
                        "Id": pipeline_arn,
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {"AwsImageBuilderPipeline": {"PipelineName": pipeline_name}},
                    }
                ],
                "Compliance": {
                    "Status": "FAILED"
                },
                "Workflow": {"Status": "NEW"},
                "RecordState": "ACTIVE",
            }
            yield finding

@registry.register_check("imagebuilder")
def imagebuilder_ebs_encryption_check(cache: dict, awsAccountId: str, awsRegion: str, awsPartition: str) -> dict:
    recipes = imagebuilder.list_image_recipes()
    recipes_list = recipes["imageRecipeSummaryList"]
    iso8601Time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for details in recipes_list:
        recipe_arn = details["arn"]
        recipe_name = details["name"]
        recipe = imagebuilder.get_image_recipe(imageRecipeArn=recipe_arn)
        device_mapping = recipe["imageRecipe"]["blockDeviceMappings"]
        list1 = device_mapping[0]
        ebs = list1["ebs"]
        ebs_encryption = ebs["encrypted"]
        if ebs_encryption == True:
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": recipe_arn + "/imagebuilder-pipeline-tests-enabled-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": recipe_arn,
                "AwsAccountId": awsAccountId,
                "Types": [
                    "Software and Configuration Checks/AWS Security Best Practices",
                    "Effects/Data Exposure",
                ],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": "INFORMATIONAL"},
                "Confidence": 99,
                "Title": "[ImageBuilder.2] Image recipes should encrypt EBS volumes",
                "Description": "Image recipe " + recipe_name + " has EBS encrypted.",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on EC2 Image Builder Security and EBS encyption refer to the How EC2 Image Builder Works section of the Amazon EC2 Image Builder Developer Guide.",
                        "Url": "https://docs.aws.amazon.com/imagebuilder/latest/userguide/how-image-builder-works.html#image-builder-components",
                    }
                },
                "ProductFields": {"Product Name": "ElectricEye"},
                "Resources": [
                    {
                        "Type": "AwsImageBuilderRecipe",
                        "Id": recipe_arn,
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {"AwsImageBuilderRecipe": {"RecipeName": recipe_name}},
                    }
                ],
                "Compliance": {
                    "Status": "PASSED"
                },
                "Workflow": {"Status": "RESOLVED"},
                "RecordState": "ARCHIVED",
            }
            yield finding
        else:
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": recipe_arn + "/imagebuilder-pipeline-tests-enabled-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": recipe_arn,
                "AwsAccountId": awsAccountId,
                "Types": [
                    "Software and Configuration Checks/AWS Security Best Practices",
                    "Effects/Data Exposure",
                ],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": "MEDIUM"},
                "Confidence": 99,
                "Title": "[ImageBuilder.2] Image recipes should encrypt EBS volumes",
                "Description": "Image recipe " + recipe_name + " does not have EBS encrypted.",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on EC2 Image Builder Security and EBS encyption refer to the How EC2 Image Builder Works section of the Amazon EC2 Image Builder Developer Guide.",
                        "Url": "https://docs.aws.amazon.com/imagebuilder/latest/userguide/how-image-builder-works.html#image-builder-components",
                    }
                },
                "ProductFields": {"Product Name": "ElectricEye"},
                "Resources": [
                    {
                        "Type": "AwsImageBuilderRecipe",
                        "Id": recipe_arn,
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {"AwsImageBuilderRecipe": {"RecipeName": recipe_name}},
                    }
                ],
                "Compliance": {
                    "Status": "FAILED"
                },
                "Workflow": {"Status": "NEW"},
                "RecordState": "ACTIVE",
            }
            yield finding
