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

import requests
import datetime
import base64
import json
from check_register import CheckRegister
from security import safe_requests

registry = CheckRegister()

API_ROOT = "https://graph.microsoft.com/v1.0"

def get_oauth_token(cache, tenantId, clientId, clientSecret):
    
    response = cache.get("get_oauth_token")
    if response:
        return response

    # Retrieve an OAuth Token for the Microsoft Graph APIs
    tokenUrl = f"https://login.microsoftonline.com/{tenantId}/oauth2/token"
    resourceAppIdUri = "https://graph.microsoft.com"

    tokenData = {
        "client_id": clientId,
        "grant_type": "client_credentials",
        "resource" : resourceAppIdUri,
        "client_secret": clientSecret
    }

    r = requests.post(tokenUrl, data=tokenData)

    if r.status_code != 200:
        raise r.reason
    else:
        token = r.json()["access_token"]

        cache["get_oauth_token"] = token
        return cache["get_oauth_token"]

def get_aad_users_with_enrichment(cache, tenantId, clientId, clientSecret):

    response = cache.get("get_aad_users_with_enrichment")
    if response:
        return response

    # Retrieve the Token from Cache
    token = get_oauth_token(cache, tenantId, clientId, clientSecret)
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    userList = []
    listUsersUrl = "https://graph.microsoft.com/v1.0/users"

    # Implement pagination here in case a shitload of Users are returned
    try:
        listusers = json.loads(safe_requests.get(listUsersUrl,headers=headers).text)
        for user in listusers["value"]:
            userList.append(user)

        while listusers["@odata.nextLink"]:
            listusers = json.loads(safe_requests.get(listusers["@odata.nextLink"], headers=headers).text)
            if "@odata.nextLink" in listusers:
                listUsersUrl = listusers["@odata.nextLink"]
            else:
                for user in listusers["value"]:
                    userList.append(user)
                break

            for user in listusers["value"]:
                userList.append(user)
    except KeyError:
        print("No more pagination for AD Users.")

    print(f"{len(userList)} AD Users found. Attempting to retrieve MFA device & Identity Protection information.")

    userList = check_user_mfa_and_risk(token, userList)
    
    # Print the len() again just in case there was an issue, not like there is anything to do about it though
    print(f"Done retrieving MFA details for {len(userList)} users!")

    cache["get_aad_users_with_enrichment"] = userList
    return cache["get_aad_users_with_enrichment"]

def check_user_mfa_and_risk(token, users):
    """
    This function receives a full list of Users adds a list of authentication methods, and
    adds Identity Protection Risky User & Sign-in (Detection) information and returns the list
    """

    headers = {
        "Authorization": f"Bearer {token}"
    }

    riskDetections = get_identity_protection_risk_detections(token)
    riskyUsers = get_identity_protection_risky_users(token)

    enrichedUsers = []

    for user in users:
        userId = user["id"]

        # Use a list comprehension to check if the User has any Risk Detections - but only if there is a list to comprehend ;)
        if riskDetections:
            userRiskDetections = [risk for risk in riskDetections if risk["userId"] == userId]
            if userRiskDetections:
                user["identityProtectionRiskDetections"] = userRiskDetections
            else:
                user["identityProtectionRiskDetections"] = []
        else:
            user["identityProtectionRiskDetections"] = []

        # Use a list comprehension to check if the User is...Risky :O - but only if there is a list to comprehend ;)
        # Use a dictionary here as there *should* only ever be one entry per user
        if riskyUsers:
            userBeingRiskyAndShit = [riskuser for riskuser in riskyUsers if riskuser["id"] == userId]
            if userBeingRiskyAndShit:
                user["identityProtectionRiskyUser"] = userBeingRiskyAndShit[0]
            else:
                user["identityProtectionRiskyUser"] = {}
        else:
            user["identityProtectionRiskyUser"] = {}

        # Get the MFA Devices now
        r = safe_requests.get(
            f"{API_ROOT}/users/{userId}/authentication/methods",
            headers=headers
        )

        if r.status_code != 200:
            print(f"Unable to get MFA for User {id} because {r.reason}")
            user["authenticationMethods"] = []
        else:
            user["authenticationMethods"] = json.loads(r.text)["value"]
            enrichedUsers.append(user)
    
    return enrichedUsers

def get_identity_protection_risk_detections(token):
    """
    Returns a list of Risk Detections from Identity Protection, these are the "Risky Sign-ins"
    """

    headers = {
        "Authorization": f"Bearer {token}"
    }

    r = safe_requests.get(
        f"{API_ROOT}/identityProtection/riskDetections",
        headers=headers
    )

    if r.status_code != 200:
        print(f"Unable to get riskDetections because {r.reason}")
        return []
    else:
        return json.loads(r.text)["value"]

def get_identity_protection_risky_users(token):
    """
    Returns a list of Risky Users from Identity Protection
    """

    headers = {
        "Authorization": f"Bearer {token}"
    }

    r = safe_requests.get(
        f"{API_ROOT}/identityProtection/riskyUsers",
        headers=headers
    )

    if r.status_code != 200:
        print(f"Unable to get riskyUsers because {r.reason}")
        return []
    else:
        return json.loads(r.text)["value"]
    
@registry.register_check("m365.aadusers")
def m365_aad_user_mfa_check(cache, awsAccountId, awsRegion, awsPartition, tenantId, clientId, clientSecret, tenantLocation):
    """
    [M365.AadUser.1] Azure Active Directory users should have at least one Multi-factor Authentication (MFA) device registered
    """
    # ISO Time
    iso8601Time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for user in get_aad_users_with_enrichment(cache, tenantId, clientId, clientSecret):
        # B64 encode all of the details for the Asset
        assetJson = json.dumps(user,default=str).encode("utf-8")
        assetB64 = base64.b64encode(assetJson)

        userId = user["id"]
        displayName = user["displayName"]
        userPrincipalName = user["userPrincipalName"]

        # By default Password is an authentication method, which is...stupid, but okay. If there is only 1 item (or somehow none)
        # then that is a failing finding and really bad
        if len(user["authenticationMethods"]) <= 1:
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": f"{tenantId}/{userId}/azure-ad-user-mfa-registered-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": f"{tenantId}/{userId}/azure-ad-user-mfa-registered-check",
                "AwsAccountId": awsAccountId,
                "Types": ["Software and Configuration Checks"],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": "HIGH"},
                "Confidence": 99,
                "Title": "[M365.AadUser.1] Azure Active Directory users should have at least one Multi-factor Authentication (MFA) device registered",
                "Description": f"Azure Active Directory user {userPrincipalName} in M365 Tenant {tenantId} does not have at least one Multi-factor Authentication (MFA) device registered. Passwords are the most common method of authenticating a sign-in to a computer or online service, but they're also the most vulnerable. People can choose easy passwords and use the same passwords for multiple sign-ins to different computers and services. To provide an extra level of security for sign-ins, you must use multifactor authentication (MFA), which uses both a password, which should be strong, and an additional verification method based on either something you have with you that isn't easily duplicated, such as a smart phone or something you uniquely and biologically have, such as your fingerprints, face, or other biometric attribute. The additional verification method isn't employed until after the user's password has been verified. With MFA, even if a strong user password is compromised, the attacker doesn't have your smart phone or your fingerprint to complete the sign-in. Ensure you understand the context behind the user, some Users may be setup just for their email and may not require MFA. That said, consider using Service Principals or Email Aliases for those purposes instead of creating an entirely new user as it can also consume license capacity and lead to higher costs and more failing findings (like this one!). Refer to the remediation instructions if this configuration is not intended.",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on setting up multi-factor authentication refer to the Multifactor authentication for Microsoft 365 section of the Microsoft 365 admin center documentation.",
                        "Url": "https://learn.microsoft.com/en-us/microsoft-365/admin/security-and-compliance/multi-factor-authentication-microsoft-365?view=o365-worldwide"
                    }
                },
                "ProductFields": {
                    "ProductName": "ElectricEye",
                    "Provider": "M365",
                    "ProviderType": "SaaS",
                    "ProviderAccountId": tenantId,
                    "AssetRegion": tenantLocation,
                    "AssetDetails": assetB64,
                    "AssetClass": "Identity & Access Management",
                    "AssetService": "Azure Active Directory",
                    "AssetComponent": "User"
                },
                "Resources": [
                    {
                        "Type": "AzureActiveDirectoryUser",
                        "Id": f"{tenantId}/{userId}",
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {
                            "Other": {
                                "TenantId": tenantId,
                                "Id": userId,
                                "DisplayName": displayName,
                                "UserPrincipalName": userPrincipalName
                            }
                        }
                    }
                ],
                "Compliance": {
                    "Status": "FAILED",
                    "RelatedRequirements": [
                        "NIST CSF V1.1 PR.AC-1",
                        "NIST SP 800-53 Rev. 4 AC-1",
                        "NIST SP 800-53 Rev. 4 AC-2",
                        "NIST SP 800-53 Rev. 4 IA-1",
                        "NIST SP 800-53 Rev. 4 IA-2",
                        "NIST SP 800-53 Rev. 4 IA-3",
                        "NIST SP 800-53 Rev. 4 IA-4",
                        "NIST SP 800-53 Rev. 4 IA-5",
                        "NIST SP 800-53 Rev. 4 IA-6",
                        "NIST SP 800-53 Rev. 4 IA-7",
                        "NIST SP 800-53 Rev. 4 IA-8",
                        "NIST SP 800-53 Rev. 4 IA-9",
                        "NIST SP 800-53 Rev. 4 IA-10",
                        "NIST SP 800-53 Rev. 4 IA-11",
                        "AICPA TSC CC6.1",
                        "AICPA TSC CC6.2",
                        "ISO 27001:2013 A.9.2.1",
                        "ISO 27001:2013 A.9.2.2",
                        "ISO 27001:2013 A.9.2.3",
                        "ISO 27001:2013 A.9.2.4",
                        "ISO 27001:2013 A.9.2.6",
                        "ISO 27001:2013 A.9.3.1",
                        "ISO 27001:2013 A.9.4.2",
                        "ISO 27001:2013 A.9.4.3"
                    ]
                },
                "Workflow": {"Status": "NEW"},
                "RecordState": "ACTIVE"
            }
            yield finding
        else:
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": f"{tenantId}/{userId}/azure-ad-user-mfa-registered-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": f"{tenantId}/{userId}/azure-ad-user-mfa-registered-check",
                "AwsAccountId": awsAccountId,
                "Types": ["Software and Configuration Checks"],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": "INFORMATIONAL"},
                "Confidence": 99,
                "Title": "[M365.AadUser.1] Azure Active Directory users should have at least one Multi-factor Authentication (MFA) device registered",
                "Description": f"Azure Active Directory user {userPrincipalName} in M365 Tenant {tenantId} does have at least one Multi-factor Authentication (MFA) device registered. MFA factors should still be reviewed to ensure they are in compliance with your Policies and are functioning.",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on setting up multi-factor authentication refer to the Multifactor authentication for Microsoft 365 section of the Microsoft 365 admin center documentation.",
                        "Url": "https://learn.microsoft.com/en-us/microsoft-365/admin/security-and-compliance/multi-factor-authentication-microsoft-365?view=o365-worldwide"
                    }
                },
                "ProductFields": {
                    "ProductName": "ElectricEye",
                    "Provider": "M365",
                    "ProviderType": "SaaS",
                    "ProviderAccountId": tenantId,
                    "AssetRegion": tenantLocation,
                    "AssetDetails": assetB64,
                    "AssetClass": "Identity & Access Management",
                    "AssetService": "Azure Active Directory",
                    "AssetComponent": "User"
                },
                "Resources": [
                    {
                        "Type": "AzureActiveDirectoryUser",
                        "Id": f"{tenantId}/{userId}",
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {
                            "Other": {
                                "TenantId": tenantId,
                                "Id": userId,
                                "DisplayName": displayName,
                                "UserPrincipalName": userPrincipalName
                            }
                        }
                    }
                ],
                "Compliance": {
                    "Status": "PASSED",
                    "RelatedRequirements": [
                        "NIST CSF V1.1 PR.AC-1",
                        "NIST SP 800-53 Rev. 4 AC-1",
                        "NIST SP 800-53 Rev. 4 AC-2",
                        "NIST SP 800-53 Rev. 4 IA-1",
                        "NIST SP 800-53 Rev. 4 IA-2",
                        "NIST SP 800-53 Rev. 4 IA-3",
                        "NIST SP 800-53 Rev. 4 IA-4",
                        "NIST SP 800-53 Rev. 4 IA-5",
                        "NIST SP 800-53 Rev. 4 IA-6",
                        "NIST SP 800-53 Rev. 4 IA-7",
                        "NIST SP 800-53 Rev. 4 IA-8",
                        "NIST SP 800-53 Rev. 4 IA-9",
                        "NIST SP 800-53 Rev. 4 IA-10",
                        "NIST SP 800-53 Rev. 4 IA-11",
                        "AICPA TSC CC6.1",
                        "AICPA TSC CC6.2",
                        "ISO 27001:2013 A.9.2.1",
                        "ISO 27001:2013 A.9.2.2",
                        "ISO 27001:2013 A.9.2.3",
                        "ISO 27001:2013 A.9.2.4",
                        "ISO 27001:2013 A.9.2.6",
                        "ISO 27001:2013 A.9.3.1",
                        "ISO 27001:2013 A.9.4.2",
                        "ISO 27001:2013 A.9.4.3"
                    ]
                },
                "Workflow": {"Status": "RESOLVED"},
                "RecordState": "ARCHIVED"
            }
            yield finding

@registry.register_check("m365.aadusers")
def m365_aad_user_phishing_resistant_mfa_check(cache, awsAccountId, awsRegion, awsPartition, tenantId, clientId, clientSecret, tenantLocation):
    """
    [M365.AadUser.2] Azure Active Directory users should have a phishing-resistant Multi-factor Authentication (MFA) device registered
    """
    phishingResistantFactors = [
        "fido2AuthenticationMethod",
        "microsoftAuthenticatorAuthenticationMethod",
        "windowsHelloForBusinessAuthenticationMethod"
    ]

    # ISO Time
    iso8601Time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for user in get_aad_users_with_enrichment(cache, tenantId, clientId, clientSecret):
        # B64 encode all of the details for the Asset
        assetJson = json.dumps(user,default=str).encode("utf-8")
        assetB64 = base64.b64encode(assetJson)

        userId = user["id"]
        displayName = user["displayName"]
        userPrincipalName = user["userPrincipalName"]

        # Microsoft considers Windows Hello, Hardware MFA (FIDO2) and Microsoft Authenticator TOTP to be "strong" or "phishing resistant"
        # Loop the list of factores, splitting the weird ass title that Microsoft gives it and check if it's one of good ones listed above
        # will fill a list so we can use it like a list comprehension and check if it has any entries
        userStrongMfa = []
        for factor in user["authenticationMethods"]:
            # the factors always start with "#microsoft.graph."
            mfaType = factor["@odata.type"].split("#microsoft.graph.")[1]
            if mfaType in phishingResistantFactors:
                userStrongMfa.append(mfaType)
            else:
                continue

        # If there are not any entries it means that either the user only has a Password ([M365.AadUser.1] checks for that) or they dont have strong MFA
        # I mean, some MFA is better than none, but still why not check for this before setting up Conditional Access Policies that'll absolutely fuck everyone up?!
        if not userStrongMfa:
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": f"{tenantId}/{userId}/azure-ad-user-phishing-resistant-mfa-registered-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": f"{tenantId}/{userId}/azure-ad-user-phishing-resistant-mfa-registered-check",
                "AwsAccountId": awsAccountId,
                "Types": ["Software and Configuration Checks"],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": "MEDIUM"},
                "Confidence": 99,
                "Title": "[M365.AadUser.2] Azure Active Directory users should have a phishing-resistant Multi-factor Authentication (MFA) device registered",
                "Description": f"Azure Active Directory user {userPrincipalName} in M365 Tenant {tenantId} does not have phishing-resistant Multi-factor Authentication (MFA) device registered. The US Office of Management and Budget (OMB) M 22-09 Memorandum for the Heads of Executive Departments and Agencies requirements are that employees use enterprise-managed identities to access applications, and that multifactor authentication protects employees from sophisticated online attacks, such as phishing. This attack method attempts to obtain and compromise credentials, with links to inauthentic sites. Multifactor authentication prevents unauthorized access to accounts and data. The memo requirements cite multifactor authentication with phishing-resistant methods: authentication processes designed to detect and prevent disclosure of authentication secrets and outputs to a website or application masquerading as a legitimate system. Microsoft recommends (based on the Memo) using FIDO2, Windows Hello, or Microsoft Authenticator - as well as Certificates or CAC/PIV devices - which are out of scope for this Electriceye Check. Ensure you understand the context behind the user, some Users may be setup just for their email and may not require MFA. That said, consider using Service Principals or Email Aliases for those purposes instead of creating an entirely new user as it can also consume license capacity and lead to higher costs and more failing findings (like this one!). Refer to the remediation instructions if this configuration is not intended.",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on setting up phishing-resistant multi-factor authentication refer to the Meet multifactor authentication requirements of memorandum 22-09 section of the Microsoft 365 Standards documentation.",
                        "Url": "https://learn.microsoft.com/en-us/azure/active-directory/standards/memo-22-09-multi-factor-authentication"
                    }
                },
                "ProductFields": {
                    "ProductName": "ElectricEye",
                    "Provider": "M365",
                    "ProviderType": "SaaS",
                    "ProviderAccountId": tenantId,
                    "AssetRegion": tenantLocation,
                    "AssetDetails": assetB64,
                    "AssetClass": "Identity & Access Management",
                    "AssetService": "Azure Active Directory",
                    "AssetComponent": "User"
                },
                "Resources": [
                    {
                        "Type": "AzureActiveDirectoryUser",
                        "Id": f"{tenantId}/{userId}",
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {
                            "Other": {
                                "TenantId": tenantId,
                                "Id": userId,
                                "DisplayName": displayName,
                                "UserPrincipalName": userPrincipalName
                            }
                        }
                    }
                ],
                "Compliance": {
                    "Status": "FAILED",
                    "RelatedRequirements": [
                        "NIST CSF V1.1 PR.AC-1",
                        "NIST SP 800-53 Rev. 4 AC-1",
                        "NIST SP 800-53 Rev. 4 AC-2",
                        "NIST SP 800-53 Rev. 4 IA-1",
                        "NIST SP 800-53 Rev. 4 IA-2",
                        "NIST SP 800-53 Rev. 4 IA-3",
                        "NIST SP 800-53 Rev. 4 IA-4",
                        "NIST SP 800-53 Rev. 4 IA-5",
                        "NIST SP 800-53 Rev. 4 IA-6",
                        "NIST SP 800-53 Rev. 4 IA-7",
                        "NIST SP 800-53 Rev. 4 IA-8",
                        "NIST SP 800-53 Rev. 4 IA-9",
                        "NIST SP 800-53 Rev. 4 IA-10",
                        "NIST SP 800-53 Rev. 4 IA-11",
                        "AICPA TSC CC6.1",
                        "AICPA TSC CC6.2",
                        "ISO 27001:2013 A.9.2.1",
                        "ISO 27001:2013 A.9.2.2",
                        "ISO 27001:2013 A.9.2.3",
                        "ISO 27001:2013 A.9.2.4",
                        "ISO 27001:2013 A.9.2.6",
                        "ISO 27001:2013 A.9.3.1",
                        "ISO 27001:2013 A.9.4.2",
                        "ISO 27001:2013 A.9.4.3"
                    ]
                },
                "Workflow": {"Status": "NEW"},
                "RecordState": "ACTIVE"
            }
            yield finding
        else:
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": f"{tenantId}/{userId}/azure-ad-user-phishing-resistant-mfa-registered-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": f"{tenantId}/{userId}/azure-ad-user-phishing-resistant-mfa-registered-check",
                "AwsAccountId": awsAccountId,
                "Types": ["Software and Configuration Checks"],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": "INFORMATIONAL"},
                "Confidence": 99,
                "Title": "[M365.AadUser.2] Azure Active Directory users should have a phishing-resistant Multi-factor Authentication (MFA) device registered",
                "Description": f"Azure Active Directory user {userPrincipalName} in M365 Tenant {tenantId} does have a phishing-resistant Multi-factor Authentication (MFA) device registered. MFA factors should still be reviewed to ensure they are in compliance with your Policies and are functioning.",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on setting up phishing-resistant multi-factor authentication refer to the Meet multifactor authentication requirements of memorandum 22-09 section of the Microsoft 365 Standards documentation.",
                        "Url": "https://learn.microsoft.com/en-us/azure/active-directory/standards/memo-22-09-multi-factor-authentication"
                    }
                },
                "ProductFields": {
                    "ProductName": "ElectricEye",
                    "Provider": "M365",
                    "ProviderType": "SaaS",
                    "ProviderAccountId": tenantId,
                    "AssetRegion": tenantLocation,
                    "AssetDetails": assetB64,
                    "AssetClass": "Identity & Access Management",
                    "AssetService": "Azure Active Directory",
                    "AssetComponent": "User"
                },
                "Resources": [
                    {
                        "Type": "AzureActiveDirectoryUser",
                        "Id": f"{tenantId}/{userId}",
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {
                            "Other": {
                                "TenantId": tenantId,
                                "Id": userId,
                                "DisplayName": displayName,
                                "UserPrincipalName": userPrincipalName
                            }
                        }
                    }
                ],
                "Compliance": {
                    "Status": "PASSED",
                    "RelatedRequirements": [
                        "NIST CSF V1.1 PR.AC-1",
                        "NIST SP 800-53 Rev. 4 AC-1",
                        "NIST SP 800-53 Rev. 4 AC-2",
                        "NIST SP 800-53 Rev. 4 IA-1",
                        "NIST SP 800-53 Rev. 4 IA-2",
                        "NIST SP 800-53 Rev. 4 IA-3",
                        "NIST SP 800-53 Rev. 4 IA-4",
                        "NIST SP 800-53 Rev. 4 IA-5",
                        "NIST SP 800-53 Rev. 4 IA-6",
                        "NIST SP 800-53 Rev. 4 IA-7",
                        "NIST SP 800-53 Rev. 4 IA-8",
                        "NIST SP 800-53 Rev. 4 IA-9",
                        "NIST SP 800-53 Rev. 4 IA-10",
                        "NIST SP 800-53 Rev. 4 IA-11",
                        "AICPA TSC CC6.1",
                        "AICPA TSC CC6.2",
                        "ISO 27001:2013 A.9.2.1",
                        "ISO 27001:2013 A.9.2.2",
                        "ISO 27001:2013 A.9.2.3",
                        "ISO 27001:2013 A.9.2.4",
                        "ISO 27001:2013 A.9.2.6",
                        "ISO 27001:2013 A.9.3.1",
                        "ISO 27001:2013 A.9.4.2",
                        "ISO 27001:2013 A.9.4.3"
                    ]
                },
                "Workflow": {"Status": "RESOLVED"},
                "RecordState": "ARCHIVED"
            }
            yield finding

@registry.register_check("m365.aadusers")
def m365_aad_user_active_identity_protection_risk_detection_check(cache, awsAccountId, awsRegion, awsPartition, tenantId, clientId, clientSecret, tenantLocation):
    """
    [M365.AadUser.3] Azure Active Directory users with active Medium or High Identity Protection Risk Detections should be investigated
    """
    # ISO Time
    iso8601Time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for user in get_aad_users_with_enrichment(cache, tenantId, clientId, clientSecret):
        # B64 encode all of the details for the Asset
        assetJson = json.dumps(user,default=str).encode("utf-8")
        assetB64 = base64.b64encode(assetJson)

        userId = user["id"]
        displayName = user["displayName"]
        userPrincipalName = user["userPrincipalName"]

        # Need to check both the "riskLevel" and the "riskState" for the Risk Detections (FKA Risky Sign-ins, which is confusing, because CA Policies call them that)
        # easier to write the different values into a list as it can grow...
        triggeringRiskLevels = ["medium", "high", "hidden", "unknownFutureValue"]
        triggeringRiskStates = ["atRisk", "confirmedCompromised", "unknownFutureValue"]

        activeRiskDetections = [risk for risk in user["identityProtectionRiskDetections"] if risk["riskLevel"] in triggeringRiskLevels and risk["riskState"] in triggeringRiskStates]

        # Use another list comprehension to get just the riskstate, we can set a higher severity finding if the riskstate == confirmedCompromised
        activeRiskStates = [risk["riskState"] for risk in activeRiskDetections]
        if "confirmedCompromised" in activeRiskStates:
            severityLabel = "CRITICAL"
        else:
            severityLabel = "HIGH"

        # If there are entries it means that a sufficient riskiness of Risk Detection has been acheived AND it is outstanding (or you confirmed the user as compromised)
        if activeRiskDetections:
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": f"{tenantId}/{userId}/azure-ad-user-identity-protection-risk-detections-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": f"{tenantId}/{userId}/azure-ad-user-identity-protection-risk-detections-check",
                "AwsAccountId": awsAccountId,
                "Types": ["Software and Configuration Checks"],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": severityLabel},
                "Confidence": 99,
                "Title": "[M365.AadUser.3] Azure Active Directory users with active Medium or High Identity Protection Risk Detections should be investigated",
                "Description": f"Azure Active Directory user {userPrincipalName} in M365 Tenant {tenantId} does have active Medium or High Identity Protection Risk Detections. Identity Protection uses the learnings Microsoft has acquired from their position in organizations with Azure Active Directory, the consumer space with Microsoft Accounts, and in gaming with Xbox to protect your users. Microsoft analyses trillions of signals per day to identify and protect customers from threats. The signals generated by and fed to Identity Protection, can be further fed into tools like Conditional Access to make access decisions, or fed back to a security information and event management (SIEM) tool for further investigation. Microsoft doesn't provide specific details about how risk is calculated. Each level of risk brings higher confidence that the user or sign-in is compromised. For example, something like one instance of unfamiliar sign-in properties for a user might not be as threatening as leaked credentials for another user. Pay attention to the factors that contribute to the Risk Detection, especially the 'riskState', if it is 'confirmedCompromised' this likely means a SOAR workflow or another security team member manually set this and it is paramount countermeasures such as session and password revocations are deployed. Refer to the remediation instructions if this configuration is not intended.",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on Identity Protection refer to the What is Identity Protection? section of the Microsoft Azure Identity Protection documentation.",
                        "Url": "https://learn.microsoft.com/en-us/azure/active-directory/identity-protection/overview-identity-protection"
                    }
                },
                "ProductFields": {
                    "ProductName": "ElectricEye",
                    "Provider": "M365",
                    "ProviderType": "SaaS",
                    "ProviderAccountId": tenantId,
                    "AssetRegion": tenantLocation,
                    "AssetDetails": assetB64,
                    "AssetClass": "Identity & Access Management",
                    "AssetService": "Azure Active Directory",
                    "AssetComponent": "User"
                },
                "Resources": [
                    {
                        "Type": "AzureActiveDirectoryUser",
                        "Id": f"{tenantId}/{userId}",
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {
                            "Other": {
                                "TenantId": tenantId,
                                "Id": userId,
                                "DisplayName": displayName,
                                "UserPrincipalName": userPrincipalName
                            }
                        }
                    }
                ],
                "Compliance": {
                    "Status": "FAILED",
                    "RelatedRequirements": [
                        "NIST CSF V1.1 DE.AE-2",
                        "NIST CSF V1.1 DE.AE-4",
                        "NIST SP 800-53 Rev. 4 AU-6",
                        "NIST SP 800-53 Rev. 4 CA-7",
                        "NIST SP 800-53 Rev. 4 CP-2",
                        "NIST SP 800-53 Rev. 4 IR-4",
                        "NIST SP 800-53 Rev. 4 RA-3",
                        "NIST SP 800-53 Rev. 4 SI-4",
                        "AICPA TSC CC7.2",
                        "AICPA TSC CC7.3",
                        "ISO 27001:2013 A.12.4.1",
                        "ISO 27001:2013 A.16.1.1",
                        "ISO 27001:2013 A.16.1.4"
                    ]
                },
                "Workflow": {"Status": "NEW"},
                "RecordState": "ACTIVE"
            }
            yield finding
        else:
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": f"{tenantId}/{userId}/azure-ad-user-identity-protection-risk-detections-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": f"{tenantId}/{userId}/azure-ad-user-identity-protection-risk-detections-check",
                "AwsAccountId": awsAccountId,
                "Types": ["Software and Configuration Checks"],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": "INFORMATIONAL"},
                "Confidence": 99,
                "Title": "[M365.AadUser.3] Azure Active Directory users with active Medium or High Identity Protection Risk Detections should be investigated",
                "Description": f"Azure Active Directory user {userPrincipalName} in M365 Tenant {tenantId} does not have active Medium or High Identity Protection Risk Detections.",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on Identity Protection refer to the What is Identity Protection? section of the Microsoft Azure Identity Protection documentation.",
                        "Url": "https://learn.microsoft.com/en-us/azure/active-directory/identity-protection/overview-identity-protection"
                    }
                },
                "ProductFields": {
                    "ProductName": "ElectricEye",
                    "Provider": "M365",
                    "ProviderType": "SaaS",
                    "ProviderAccountId": tenantId,
                    "AssetRegion": tenantLocation,
                    "AssetDetails": assetB64,
                    "AssetClass": "Identity & Access Management",
                    "AssetService": "Azure Active Directory",
                    "AssetComponent": "User"
                },
                "Resources": [
                    {
                        "Type": "AzureActiveDirectoryUser",
                        "Id": f"{tenantId}/{userId}",
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {
                            "Other": {
                                "TenantId": tenantId,
                                "Id": userId,
                                "DisplayName": displayName,
                                "UserPrincipalName": userPrincipalName
                            }
                        }
                    }
                ],
                "Compliance": {
                    "Status": "PASSED",
                    "RelatedRequirements": [
                        "NIST CSF V1.1 DE.AE-2",
                        "NIST CSF V1.1 DE.AE-4",
                        "NIST SP 800-53 Rev. 4 AU-6",
                        "NIST SP 800-53 Rev. 4 CA-7",
                        "NIST SP 800-53 Rev. 4 CP-2",
                        "NIST SP 800-53 Rev. 4 IR-4",
                        "NIST SP 800-53 Rev. 4 RA-3",
                        "NIST SP 800-53 Rev. 4 SI-4",
                        "AICPA TSC CC7.2",
                        "AICPA TSC CC7.3",
                        "ISO 27001:2013 A.12.4.1",
                        "ISO 27001:2013 A.16.1.1",
                        "ISO 27001:2013 A.16.1.4"
                    ]
                },
                "Workflow": {"Status": "RESOLVED"},
                "RecordState": "ARCHIVED"
            }
            yield finding

@registry.register_check("m365.aadusers")
def m365_aad_user_active_identity_protection_risky_user_check(cache, awsAccountId, awsRegion, awsPartition, tenantId, clientId, clientSecret, tenantLocation):
    """
    [M365.AadUser.4] Azure Active Directory users that are active Risky Users in Identity Protection should be investigated
    """
    # ISO Time
    iso8601Time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for user in get_aad_users_with_enrichment(cache, tenantId, clientId, clientSecret):
        # B64 encode all of the details for the Asset
        assetJson = json.dumps(user,default=str).encode("utf-8")
        assetB64 = base64.b64encode(assetJson)

        userId = user["id"]
        displayName = user["displayName"]
        userPrincipalName = user["userPrincipalName"]

        # Risky User information is written as a dictionary, if it is empty then they're not a risky user. If they are a Risky User we need to check their riskState
        # there is likely overlap here between Risk Detections as well but...you never know with Microsoft, deadass yo word to your mother
        if user["identityProtectionRiskyUser"]:
            if user["identityProtectionRiskyUser"]["riskState"] == "atRisk":
                isRiskyUser = True
                # Set the severity
                if user["identityProtectionRiskyUser"]["riskLevel"] == "high":
                    severityLabel = "HIGH"
                elif user["identityProtectionRiskyUser"]["riskLevel"] == "medium":
                    severityLabel = "MEDIUM"
                else:
                    severityLabel = "LOW"
            else:
                isRiskyUser = False
        else:
            isRiskyUser = False

        if isRiskyUser is True:
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": f"{tenantId}/{userId}/azure-ad-user-identity-protection-risky-user-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": f"{tenantId}/{userId}/azure-ad-user-identity-protection-risky-user-check",
                "AwsAccountId": awsAccountId,
                "Types": ["Software and Configuration Checks"],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": severityLabel},
                "Confidence": 99,
                "Title": "[M365.AadUser.4] Azure Active Directory users that are active Risky Users in Identity Protection should be investigated",
                "Description": f"Azure Active Directory user {userPrincipalName} in M365 Tenant {tenantId} is an active Risky User in Identity Protection. Identity Protection uses the learnings Microsoft has acquired from their position in organizations with Azure Active Directory, the consumer space with Microsoft Accounts, and in gaming with Xbox to protect your users. Microsoft analyses trillions of signals per day to identify and protect customers from threats. The signals generated by and fed to Identity Protection, can be further fed into tools like Conditional Access to make access decisions, or fed back to a security information and event management (SIEM) tool for further investigation. Microsoft doesn't provide specific details about how risk is calculated. Each level of risk brings higher confidence that the user or sign-in is compromised. For example, something like one instance of unfamiliar sign-in properties for a user might not be as threatening as leaked credentials for another user. The affected User may or may not have associated Risk Events, pay attention to the last time their Risk changed within Identity Protection and at the very least ensure they have a phishing-resistant MFA device and reset their password and revoke all sessions. Refer to the remediation instructions if this configuration is not intended.",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on Identity Protection refer to the What is Identity Protection? section of the Microsoft Azure Identity Protection documentation.",
                        "Url": "https://learn.microsoft.com/en-us/azure/active-directory/identity-protection/overview-identity-protection"
                    }
                },
                "ProductFields": {
                    "ProductName": "ElectricEye",
                    "Provider": "M365",
                    "ProviderType": "SaaS",
                    "ProviderAccountId": tenantId,
                    "AssetRegion": tenantLocation,
                    "AssetDetails": assetB64,
                    "AssetClass": "Identity & Access Management",
                    "AssetService": "Azure Active Directory",
                    "AssetComponent": "User"
                },
                "Resources": [
                    {
                        "Type": "AzureActiveDirectoryUser",
                        "Id": f"{tenantId}/{userId}",
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {
                            "Other": {
                                "TenantId": tenantId,
                                "Id": userId,
                                "DisplayName": displayName,
                                "UserPrincipalName": userPrincipalName
                            }
                        }
                    }
                ],
                "Compliance": {
                    "Status": "FAILED",
                    "RelatedRequirements": [
                        "NIST CSF V1.1 DE.AE-2",
                        "NIST CSF V1.1 DE.AE-4",
                        "NIST SP 800-53 Rev. 4 AU-6",
                        "NIST SP 800-53 Rev. 4 CA-7",
                        "NIST SP 800-53 Rev. 4 CP-2",
                        "NIST SP 800-53 Rev. 4 IR-4",
                        "NIST SP 800-53 Rev. 4 RA-3",
                        "NIST SP 800-53 Rev. 4 SI-4",
                        "AICPA TSC CC7.2",
                        "AICPA TSC CC7.3",
                        "ISO 27001:2013 A.12.4.1",
                        "ISO 27001:2013 A.16.1.1",
                        "ISO 27001:2013 A.16.1.4"
                    ]
                },
                "Workflow": {"Status": "NEW"},
                "RecordState": "ACTIVE"
            }
            yield finding
        else:
            finding = {
                "SchemaVersion": "2018-10-08",
                "Id": f"{tenantId}/{userId}/azure-ad-user-identity-protection-risky-user-check",
                "ProductArn": f"arn:{awsPartition}:securityhub:{awsRegion}:{awsAccountId}:product/{awsAccountId}/default",
                "GeneratorId": f"{tenantId}/{userId}/azure-ad-user-identity-protection-risky-user-check",
                "AwsAccountId": awsAccountId,
                "Types": ["Software and Configuration Checks"],
                "FirstObservedAt": iso8601Time,
                "CreatedAt": iso8601Time,
                "UpdatedAt": iso8601Time,
                "Severity": {"Label": "INFORMATIONAL"},
                "Confidence": 99,
                "Title": "[M365.AadUser.4] Azure Active Directory users that are active Risky Users in Identity Protection should be investigated",
                "Description": f"Azure Active Directory user {userPrincipalName} in M365 Tenant {tenantId} is not an active Risky User in Identity Protection.",
                "Remediation": {
                    "Recommendation": {
                        "Text": "For more information on Identity Protection refer to the What is Identity Protection? section of the Microsoft Azure Identity Protection documentation.",
                        "Url": "https://learn.microsoft.com/en-us/azure/active-directory/identity-protection/overview-identity-protection"
                    }
                },
                "ProductFields": {
                    "ProductName": "ElectricEye",
                    "Provider": "M365",
                    "ProviderType": "SaaS",
                    "ProviderAccountId": tenantId,
                    "AssetRegion": tenantLocation,
                    "AssetDetails": assetB64,
                    "AssetClass": "Identity & Access Management",
                    "AssetService": "Azure Active Directory",
                    "AssetComponent": "User"
                },
                "Resources": [
                    {
                        "Type": "AzureActiveDirectoryUser",
                        "Id": f"{tenantId}/{userId}",
                        "Partition": awsPartition,
                        "Region": awsRegion,
                        "Details": {
                            "Other": {
                                "TenantId": tenantId,
                                "Id": userId,
                                "DisplayName": displayName,
                                "UserPrincipalName": userPrincipalName
                            }
                        }
                    }
                ],
                "Compliance": {
                    "Status": "PASSED",
                    "RelatedRequirements": [
                        "NIST CSF V1.1 DE.AE-2",
                        "NIST CSF V1.1 DE.AE-4",
                        "NIST SP 800-53 Rev. 4 AU-6",
                        "NIST SP 800-53 Rev. 4 CA-7",
                        "NIST SP 800-53 Rev. 4 CP-2",
                        "NIST SP 800-53 Rev. 4 IR-4",
                        "NIST SP 800-53 Rev. 4 RA-3",
                        "NIST SP 800-53 Rev. 4 SI-4",
                        "AICPA TSC CC7.2",
                        "AICPA TSC CC7.3",
                        "ISO 27001:2013 A.12.4.1",
                        "ISO 27001:2013 A.16.1.1",
                        "ISO 27001:2013 A.16.1.4"
                    ]
                },
                "Workflow": {"Status": "RESOLVED"},
                "RecordState": "ARCHIVED"
            }
            yield finding

## END ??
