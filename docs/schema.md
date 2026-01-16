# Snapshot JSON schema (informal)

This document describes the expected shape of the snapshot JSON written to S3.

Top-level keys

- collectedAt: ISO-8601 UTC timestamp when the snapshot was taken.
- region: AWS region of the snapshot.
- vpcId: VPC id if the snapshot was limited to one VPC; otherwise null.
- vpcs: array of raw VPC objects from EC2 DescribeVpcs (kept for reference).
- subnets: array of normalized subnet objects:
  - SubnetId, VpcId, CidrBlock, AvailabilityZone, AvailableIpAddressCount
- routeTables: array of normalized route table objects:
  - RouteTableId, VpcId, Associations (list of association ids), Routes (minimal fields)
- securityGroups: array of normalized security group objects:
  - GroupId, GroupName, VpcId, Description
- networkInterfaces: array of normalized ENI objects:
  - NetworkInterfaceId, VpcId, SubnetId, Description, PrivateIpAddress
- notes: simple metadata object, e.g. source and optional TTL

Storage

Snapshots are stored under the configured S3 prefix in the following layout:

snapshots/<region>/<vpcId-or-all-vpcs>/<timestamp>.json

Retention

Add S3 lifecycle rules to expire or transition snapshots older than your retention window.
