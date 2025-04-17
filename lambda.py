import boto3
import csv
import io
from datetime import datetime, timedelta
import os

# AWS clients
lambda_client = boto3.client('lambda')
logs_client = boto3.client('logs')
cloudwatch_client = boto3.client('cloudwatch')
iam_client = boto3.client('iam')
s3_client = boto3.client('s3')

# Environment variables
S3_BUCKET = os.environ['S3_BUCKET_NAME']

# Config: list of lambda names to check — leave empty to check all
lambda_names_to_check = []  # Example: ['my-lambda-1', 'my-lambda-2']

# Date range for CloudWatch metrics (last 2 years)
end_time = datetime.utcnow()
start_time = end_time - timedelta(days=730)


# Fetch all Lambda functions
def get_all_lambda_functions():
    functions = []
    paginator = lambda_client.get_paginator('list_functions')
    for page in paginator.paginate():
        for fn in page['Functions']:
            if not lambda_names_to_check or fn['FunctionName'] in lambda_names_to_check:
                functions.append(fn)
    return functions


# Check if CloudWatch Logs exist for Lambda
def check_log_group(function_name):
    log_group_name = f'/aws/lambda/{function_name}'
    try:
        response = logs_client.describe_log_groups(logGroupNamePrefix=log_group_name)
        for log_group in response.get('logGroups', []):
            if log_group['logGroupName'] == log_group_name:
                creation_time = datetime.utcfromtimestamp(log_group['creationTime'] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                return True, creation_time
        return False, None
    except Exception:
        return False, None


# Get invocation and error metrics from CloudWatch
def get_lambda_metrics(function_name):
    try:
        invocations_response = cloudwatch_client.get_metric_statistics(
            Namespace='AWS/Lambda',
            MetricName='Invocations',
            Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400 * 30,
            Statistics=['Sum']
        )
        total_invocations = sum(dp['Sum'] for dp in invocations_response['Datapoints'])

        errors_response = cloudwatch_client.get_metric_statistics(
            Namespace='AWS/Lambda',
            MetricName='Errors',
            Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400 * 30,
            Statistics=['Sum']
        )
        total_errors = sum(dp['Sum'] for dp in errors_response['Datapoints'])

        return int(total_invocations), int(total_errors)
    except Exception:
        return 0, 0


# Get last successful invocation time via CloudWatch logs
def get_last_success_time(function_name):
    log_group_name = f'/aws/lambda/{function_name}'
    try:
        response = logs_client.describe_log_streams(
            logGroupName=log_group_name,
            orderBy='LastEventTime',
            descending=True,
            limit=1
        )
        if response.get('logStreams'):
            last_event_timestamp = response['logStreams'][0].get('lastEventTimestamp')
            if last_event_timestamp:
                last_success = datetime.utcfromtimestamp(last_event_timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
                return last_success
        return 'N/A'
    except Exception:
        return 'N/A'


# Get tags for Lambda
def get_lambda_tags(function_arn):
    try:
        response = lambda_client.list_tags(Resource=function_arn)
        return response.get('Tags', {})
    except Exception:
        return {}


# Get execution role and last used info
def get_role_info(role_arn):
    try:
        role_name = role_arn.split('/')[-1]
        response = iam_client.get_role(RoleName=role_name)
        last_used = response['Role'].get('RoleLastUsed', {}).get('LastUsedDate')
        last_used_date = last_used.strftime('%Y-%m-%d %H:%M:%S') if last_used else 'Never Used'
        return role_name, last_used_date
    except Exception:
        return 'N/A', 'N/A'


# Write report to S3
def write_to_s3(data):
    csv_buffer = io.StringIO()
    fieldnames = ['FunctionName', 'Runtime', 'LastModified', 'LogGroupEnabled', 'LogGroupCreationDate',
                  'TotalInvocations', 'TotalErrors', 'LastSuccessTime', 'Tags', 'ExecutionRole', 'RoleLastUsedDate']
    writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in data:
        writer.writerow(row)

    now = datetime.utcnow().strftime('%Y-%m-%d_%H-%M-%S')
    s3_key = f'lambda-inventory-reports/lambda_inventory_report_{now}.csv'
    s3_client.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=csv_buffer.getvalue())

    print(f"✅ Report uploaded to s3://{S3_BUCKET}/{s3_key}")


# Lambda handler
def lambda_handler(event, context):
    functions = get_all_lambda_functions()
    result = []

    for fn in functions:
        function_name = fn['FunctionName']
        runtime = fn['Runtime']
        last_modified = fn['LastModified']
        role_arn = fn['Role']

        print(f"⏳ Processing Lambda: {function_name}")

        log_enabled, log_creation_date = check_log_group(function_name)
        invocations, errors = get_lambda_metrics(function_name)
        last_success_time = get_last_success_time(function_name)
        tags = get_lambda_tags(fn['FunctionArn'])
        role_name, role_last_used = get_role_info(role_arn)

        result.append({
            'FunctionName': function_name,
            'Runtime': runtime,
            'LastModified': last_modified,
            'LogGroupEnabled': 'Yes' if log_enabled else 'No',
            'LogGroupCreationDate': log_creation_date if log_enabled else 'N/A',
            'TotalInvocations': invocations,
            'TotalErrors': errors,
            'LastSuccessTime': last_success_time,
            'Tags': tags,
            'ExecutionRole': role_name,
            'RoleLastUsedDate': role_last_used
        })

    write_to_s3(result)
    return {
        'statusCode': 200,
        'body': f'Lambda Inventory Report generated and uploaded to s3://{S3_BUCKET}/'
    }
