import json
import os
import logging
import traceback
from datetime import datetime, timezone, timedelta

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

METRIC_NAMESPACE = os.environ.get('METRIC_NAMESPACE', 'LambdaVPCLookup')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')

# Simple in-memory cache for assumed-role sessions
# Structure: { role_arn: {'session': boto3.Session, 'expires_at': datetime} }
ASSUME_ROLE_CACHE = {}
CACHE_SAFETY_MARGIN = timedelta(seconds=30)


def get_session_from_assumed_role(role_arn, region_name=None):
    """Assume the provided role ARN and return a boto3.Session using temporary creds.

    This function caches the created session in-memory until the credentials expire to
    reduce STS calls across warm Lambda invocations.
    """
    now = datetime.now(timezone.utc)
    entry = ASSUME_ROLE_CACHE.get(role_arn)
    if entry:
        expires_at = entry.get('expires_at')
        if expires_at and (expires_at - now) > CACHE_SAFETY_MARGIN:
            logger.debug({'event': 'assume_role_cache_hit', 'role': role_arn})
            return entry['session']

    sts = boto3.client('sts', region_name=region_name)
    resp = sts.assume_role(RoleArn=role_arn, RoleSessionName='VpcLookupSession')
    creds = resp['Credentials']
    expires_at = creds.get('Expiration')

    session = boto3.Session(
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'],
        region_name=region_name,
    )

    # store in cache with expiration
    ASSUME_ROLE_CACHE[role_arn] = {'session': session, 'expires_at': expires_at}
    logger.debug({'event': 'assume_role_cached', 'role': role_arn, 'expires_at': str(expires_at)})
    return session


def get_ec2_client(region_name=None, assume_role_arn=None):
    if assume_role_arn:
        session = get_session_from_assumed_role(assume_role_arn, region_name=region_name)
        return session.client('ec2')
    return boto3.client('ec2', region_name=region_name)


def get_s3_client(region_name=None, assume_role_arn=None):
    if assume_role_arn:
        session = get_session_from_assumed_role(assume_role_arn, region_name=region_name)
        return session.client('s3')
    return boto3.client('s3', region_name=region_name)


def get_cloudwatch_client(region_name=None):
    return boto3.client('cloudwatch', region_name=region_name)


def get_sns_client(region_name=None):
    return boto3.client('sns', region_name=region_name)


def publish_metric(region, metric_name, value, unit='Count'):
    try:
        cw = get_cloudwatch_client(region_name=region)
        cw.put_metric_data(Namespace=METRIC_NAMESPACE, MetricData=[{'MetricName': metric_name, 'Value': value, 'Unit': unit}])
        logger.info({'event': 'metric_published', 'metric': metric_name, 'value': value})
    except Exception:
        logger.exception('failed to publish metric')


def notify_failure(region, message, subject='Lambda VPC Lookup Failure'):
    if not SNS_TOPIC_ARN:
        logger.warning('SNS_TOPIC_ARN not configured; skipping failure notification')
        return
    try:
        sns = get_sns_client(region_name=region)
        sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=message)
        logger.info({'event': 'sns_published', 'topic': SNS_TOPIC_ARN})
    except Exception:
        logger.exception('failed to publish SNS notification')


def normalize_subnet(s):
    return {
        'SubnetId': s.get('SubnetId'),
        'VpcId': s.get('VpcId'),
        'CidrBlock': s.get('CidrBlock'),
        'AvailabilityZone': s.get('AvailabilityZone'),
        'AvailableIpAddressCount': s.get('AvailableIpAddressCount')
    }


def normalize_route_table(rt):
    return {
        'RouteTableId': rt.get('RouteTableId'),
        'VpcId': rt.get('VpcId'),
        'Associations': [a.get('RouteTableAssociationId') for a in rt.get('Associations', [])],
        'Routes': [{k: v for k, v in r.items() if k in ('DestinationCidrBlock', 'GatewayId', 'InstanceId', 'NatGatewayId')} for r in rt.get('Routes', [])]
    }


def normalize_sg(sg):
    return {
        'GroupId': sg.get('GroupId'),
        'GroupName': sg.get('GroupName'),
        'VpcId': sg.get('VpcId'),
        'Description': sg.get('Description')
    }


def normalize_eni(eni):
    return {
        'NetworkInterfaceId': eni.get('NetworkInterfaceId'),
        'VpcId': eni.get('VpcId'),
        'SubnetId': eni.get('SubnetId'),
        'Description': eni.get('Description'),
        'PrivateIpAddress': eni.get('PrivateIpAddress')
    }


def collect_vpc_snapshot(ec2_client, region, vpc_id=None):
    snapshot = {'collectedAt': datetime.now(timezone.utc).isoformat(), 'region': region, 'vpcId': vpc_id}

    # VPCs
    if vpc_id:
        vpcs = ec2_client.describe_vpcs(VpcIds=[vpc_id]).get('Vpcs', [])
    else:
        vpcs = ec2_client.describe_vpcs().get('Vpcs', [])
    snapshot['vpcs'] = vpcs

    # Subnets
    if vpc_id:
        subnets = ec2_client.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]).get('Subnets', [])
    else:
        subnets = ec2_client.describe_subnets().get('Subnets', [])
    snapshot['subnets'] = [normalize_subnet(s) for s in subnets]

    # Route tables
    if vpc_id:
        rts = ec2_client.describe_route_tables(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]).get('RouteTables', [])
    else:
        rts = ec2_client.describe_route_tables().get('RouteTables', [])
    snapshot['routeTables'] = [normalize_route_table(r) for r in rts]

    # Security groups
    if vpc_id:
        sgs = ec2_client.describe_security_groups(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]).get('SecurityGroups', [])
    else:
        sgs = ec2_client.describe_security_groups().get('SecurityGroups', [])
    snapshot['securityGroups'] = [normalize_sg(s) for s in sgs]

    # Network interfaces
    if vpc_id:
        enis = ec2_client.describe_network_interfaces(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]).get('NetworkInterfaces', [])
    else:
        enis = ec2_client.describe_network_interfaces().get('NetworkInterfaces', [])
    snapshot['networkInterfaces'] = [normalize_eni(e) for e in enis]

    snapshot['notes'] = {'source': 'Describe* EC2 APIs'}
    return snapshot


def write_snapshot_to_s3(s3_client, bucket, prefix, region, vpc_id, snapshot):
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    key_prefix = f"{prefix.rstrip('/')}/" if prefix else ''
    key_vpc = vpc_id or 'all-vpcs'
    key = f"{key_prefix}{region}/{key_vpc}/{ts}.json"

    body = json.dumps(snapshot, default=str)
    s3_client.put_object(Bucket=bucket, Key=key, Body=body, ContentType='application/json')
    return key


def handler(event, context):
    """Lambda handler.

    Event shape (optional keys):
      - region: overrides default region
      - vpcId: target VPC id (optional)
      - bucket: S3 bucket to write into (required)
      - prefix: S3 key prefix (optional)
      - roleArn: optional role to assume for cross-account lookups

    """
    # Inputs
    region = event.get('region') or os.environ.get('AWS_REGION') or 'us-east-1'
    vpc_id = event.get('vpcId')
    bucket = event.get('bucket') or os.environ.get('SNAPSHOT_BUCKET')
    prefix = event.get('prefix', 'snapshots')
    role_arn = event.get('roleArn') or os.environ.get('ASSUME_ROLE_ARN')

    log_context = {'region': region, 'vpcId': vpc_id, 'bucket': bucket, 'roleArn': role_arn}
    logger.info({'event': 'invoke', **log_context})

    if not bucket:
        raise ValueError('Target S3 bucket must be provided via event.bucket or SNAPSHOT_BUCKET env var')

    try:
        ec2 = get_ec2_client(region_name=region, assume_role_arn=role_arn)
        s3 = get_s3_client(region_name=region, assume_role_arn=role_arn)

        snapshot = collect_vpc_snapshot(ec2, region, vpc_id=vpc_id)
        key = write_snapshot_to_s3(s3, bucket, prefix, region, vpc_id, snapshot)

        publish_metric(region, 'SnapshotSuccess', 1)
        logger.info({'event': 'success', 's3_key': key})
        return {'bucket': bucket, 'key': key, 'size': len(json.dumps(snapshot))}

    except Exception as e:
        tb = traceback.format_exc()
        logger.error({'event': 'failure', 'error': str(e), 'trace': tb})
        publish_metric(region, 'SnapshotFailure', 1)
        notify_failure(region, json.dumps({'error': str(e), 'trace': tb, 'context': log_context}))
        raise
