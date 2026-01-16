import json
from unittest import mock

import pytest

from src import lambda_function


class DummyEC2:
    def __init__(self):
        pass

    def describe_vpcs(self, VpcIds=None):
        return {'Vpcs': [{'VpcId': 'vpc-1', 'CidrBlock': '10.0.0.0/16'}]}

    def describe_subnets(self, Filters=None):
        return {'Subnets': [{'SubnetId': 'subnet-1', 'VpcId': 'vpc-1', 'CidrBlock': '10.0.1.0/24', 'AvailabilityZone': 'us-east-1a', 'AvailableIpAddressCount': 250}]}

    def describe_route_tables(self, Filters=None):
        return {'RouteTables': [{'RouteTableId': 'rtb-1', 'VpcId': 'vpc-1', 'Associations': [{'RouteTableAssociationId': 'rtbassoc-1'}], 'Routes': [{'DestinationCidrBlock': '0.0.0.0/0', 'GatewayId': 'igw-1'}]}]}

    def describe_security_groups(self, Filters=None):
        return {'SecurityGroups': [{'GroupId': 'sg-1', 'GroupName': 'default', 'VpcId': 'vpc-1', 'Description': 'default'}]}

    def describe_network_interfaces(self, Filters=None):
        return {'NetworkInterfaces': [{'NetworkInterfaceId': 'eni-1', 'VpcId': 'vpc-1', 'SubnetId': 'subnet-1', 'Description': 'eni', 'PrivateIpAddress': '10.0.1.5'}]}


class DummyS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.objects[Key] = Body
        return {'ETag': '"dummy"'}


@mock.patch('src.lambda_function.get_ec2_client')
@mock.patch('src.lambda_function.get_s3_client')
def test_handler_writes_snapshot(get_s3_client_mock, get_ec2_client_mock):
    ec2 = DummyEC2()
    s3 = DummyS3()
    get_ec2_client_mock.return_value = ec2
    get_s3_client_mock.return_value = s3

    event = {'region': 'us-east-1', 'vpcId': 'vpc-1', 'bucket': 'my-bucket', 'prefix': 'snapshots'}
    res = lambda_function.handler(event, None)

    assert res['bucket'] == 'my-bucket'
    assert res['key'].startswith('snapshots/us-east-1/vpc-1')

    # verify object stored
    assert any(k.startswith('snapshots/us-east-1/vpc-1') for k in s3.objects.keys())
    # verify JSON contains vpcId
    stored = list(s3.objects.values())[0]
    data = json.loads(stored)
    assert data['vpcId'] == 'vpc-1'
