import json
import boto3

import moto

from src import lambda_function


@moto.mock_aws
def test_integration_writes_snapshot():
    region = 'us-east-1'

    # create a mocked S3 bucket
    s3 = boto3.client('s3', region_name=region)
    s3.create_bucket(Bucket='my-bucket')

    # create a mocked VPC and subnet
    ec2 = boto3.client('ec2', region_name=region)
    vpc = ec2.create_vpc(CidrBlock='10.0.0.0/16')
    vpc_id = vpc['Vpc']['VpcId']
    ec2.create_subnet(VpcId=vpc_id, CidrBlock='10.0.1.0/24', AvailabilityZone=region + 'a')

    event = {'region': region, 'vpcId': vpc_id, 'bucket': 'my-bucket', 'prefix': 'snapshots'}
    res = lambda_function.handler(event, None)

    # list objects and ensure at least one snapshot exists
    objs = s3.list_objects_v2(Bucket='my-bucket', Prefix=f"snapshots/{region}/{vpc_id}")
    assert objs.get('KeyCount', 0) > 0

    # fetch stored object and assert it contains the vpcId
    key = objs['Contents'][0]['Key']
    stored = s3.get_object(Bucket='my-bucket', Key=key)['Body'].read()
    data = json.loads(stored)
    assert data['vpcId'] == vpc_id
