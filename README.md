# Lambda-VPC-Lookup-S3

A small, focused AWS project that looks up VPC-related metadata and stores or exposes results via S3. This repository contains infrastructure and application artifacts to run a Lambda function that performs VPC lookups (for example: subnets, route tables, security groups, and attached resources) and writes the results to an S3 bucket for later analysis or downstream jobs.

## Project goals

- Provide a lightweight, secure Lambda that can collect VPC metadata across an account or from a specified VPC and persist snapshots to S3.
- Be easy to deploy (IaC-first), test locally, and run on a schedule or on-demand.
- Follow least-privilege IAM practices and work from within a VPC when necessary.
- Produce human- and machine-friendly output (JSON), with clear lifecycle and monitoring guidance.

## High-level approach

1. A Lambda function queries the AWS APIs (EC2 primarily) for VPC information.
2. The function formats and normalizes the discovered metadata (subnets, route tables, security groups, ENIs, attached gateways, etc.).
3. Results are written to an S3 prefix (timestamped JSON files). Optionally a small index file is updated for quick lookups.
4. The Lambda is deployed via Infrastructure-as-Code (CloudFormation, CDK, or Terraform — choose one that fits your stack). The IaC creates the Lambda, execution role, S3 bucket, and any necessary VPC configuration.
5. The function runs either on a schedule (EventBridge / CloudWatch Events), or in response to an API/GitHub action or manual invocation.

## Components

- Lambda function
  - Purpose: perform the VPC metadata discovery and write JSON results to S3.
  - Inputs: VPC ID (optional), region (optional), filters (optional).
  - Output: JSON stored at s3://<bucket>/<prefix>/<region>-<vpc>-<timestamp>.json
- S3 bucket
  - Stores snapshots and optionally an index or metadata catalog.
  - Use server-side encryption (SSE-S3 or SSE-KMS) and bucket policies to control access.
- IAM role and policies
  - Least-privilege role for Lambda to call EC2 Describe* APIs and put objects into S3.
- Optional: EventBridge rule for scheduled snapshots, CloudWatch metrics and logs, SNS for failure alerts.

## Data contract (snapshot shape)

Example simplified JSON structure:

```json
{
  "collectedAt": "2026-01-16T12:00:00Z",
  "region": "us-east-1",
  "vpcId": "vpc-0123456789abcdef0",
  "subnets": [ ... ],
  "routeTables": [ ... ],
  "securityGroups": [ ... ],
  "networkInterfaces": [ ... ],
  "notes": {
    "source": "Describe* API calls",
    "ttl": "optional metadata"
  }
}
```

Keep snapshots compact, avoid embedding large nested structures unless necessary — prefer references (IDs) and minimal descriptive fields.

## Security and IAM

- Lambda execution role should be scoped to required Describe* EC2 actions and PutObject/PutObjectAcl on the target S3 prefix.
- Use an S3 bucket policy to restrict writes to the Lambda role and restrict reads to authorized principals.
- If the Lambda executes inside a VPC to reach private resources, give it appropriate subnet and security group configuration and attach VPC endpoints for S3 where useful.
- Prefer SSE-KMS for sensitive environments; rotate keys according to policy.

## Deployment options

- CloudFormation / SAM: small template to create function, role, bucket, event rule.
- CDK (TypeScript/Python): more programmable, recommended if you already use CDK.
- Terraform: if your org uses Terraform for infra.

Suggested minimal CloudFormation resources:

- AWS::Lambda::Function
- AWS::IAM::Role (Lambda execution role)
- AWS::S3::Bucket
- AWS::Events::Rule (optional scheduled snapshot)
- (Optional) AWS::Logs::LogGroup, AWS::SNS::Topic for alerts

## Local development and testing

1. Implement the Lambda handler in the language of your choice. Keep I/O abstracted so you can unit test logic without AWS calls.
2. Use dependency injection or a small adapter layer for AWS SDK calls so you can mock responses.
3. For local integration testing, consider SAM CLI (`sam local invoke`) or localstack to emulate AWS APIs and S3.

Quick test checklist:

- Unit tests for normalization logic (happy path + missing fields).
- Integration test that writes to a test S3 bucket (clean up after run).
- Linting and static checks per language (flake8, eslint, mypy, etc.).

## Error handling and retries

- Treat AWS throttling and transient errors as retryable with exponential backoff.
- Fail fast on missing permissions (log a clear diagnostic and send an alert if configured).
- Validate that outputs are JSON-serializable; if a resource cannot be serialized, add a short warning field instead of crashing.

## Observability

- Push basic metrics: snapshot success/failure, objects written, duration.
- Enable CloudWatch Logs for the Lambda and use structured logging (JSON) to make queries simpler.
- Consider a small CloudWatch dashboard showing last run, run duration, and error count.

## Cost considerations

- Lambda cost: small if function is short and invoked infrequently.
- S3 storage: snapshots can accumulate; use lifecycle rules to transition to Glacier or delete after retention period.
- API calls: Describe* calls are cheap but if running across many regions or many VPCs frequently, they add up.

## Edge cases and caveats

- Cross-account lookups require role assumption patterns (STS:AssumeRole).
- If run inside a VPC without S3 endpoints, Lambda needs NAT or VPC endpoints to reach S3 and AWS APIs.
- Large VPCs can produce large JSON snapshots — consider paging or streaming writes.

## Recommended next steps for this repo

1. Pick an implementation language and add a minimal Lambda handler that performs DescribeVpcs/DescribeSubnets and writes one JSON to S3.
2. Add an IaC template (CloudFormation/SAM/CDK/Terraform) to create the Lambda, role, and S3 bucket.
3. Add unit tests for the normalization/serialization logic and a simple integration test that writes to a temporary bucket.
4. Add CI that runs lint/tests and a CD pipeline (deploy to a sandbox account) if desired.

## Example: minimal usage

Invoke with a payload to specify region or VPC, e.g. (if using an API gateway or direct invoke):

```json
{
  "region": "us-east-1",
  "vpcId": "vpc-0123456789abcdef0"
}
```

The function writes: s3://<bucket>/snapshots/us-east-1/vpc-0123456789abcdef0/2026-01-16T12:00:00Z.json

## Files you should add in this repo

- src/ (Lambda handler code)
- infra/ (CloudFormation/SAM/CDK/Terraform templates)
- tests/ (unit + integration tests)
- .github/workflows/ (CI that runs tests and optionally deploys)
- docs/ (any design notes or JSON schema definitions)

## Contributing

Open a PR with clear motivation, tests for new logic, and any infra changes split into a separate commit.

## License

Specify your project's license here (e.g. MIT, Apache-2.0).

---
