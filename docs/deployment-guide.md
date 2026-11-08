# CloudDeploy - Step-by-Step AWS Deployment Guide

This guide provides end-to-end instructions for deploying CloudDeploy to AWS using GitHub Actions OIDC authentication, Amazon ECR, and an AWS EC2 instance.

---

## 1. Prerequisites

- An active **AWS Account** with permissions to manage IAM, EC2, ECR, SSM, and CloudWatch.
- A **GitHub Account** and repository named `CloudDeploy-AWS-CICD`.
- **AWS CLI v2** configured locally (optional, commands can also be run in AWS CloudShell).

---

## 2. Step 1: Configure AWS GitHub OIDC Identity Provider

GitHub Actions connects to AWS using OpenID Connect (OIDC), eliminating the need for long-lived access keys.

### 2.1 Check or Create OIDC Provider
In the AWS CLI or CloudShell:
```bash
# Check if GitHub OIDC provider already exists
aws iam list-open-id-connect-providers

# If not present, create it:
aws iam create-open-id-connect-provider \
  --url "https://token.actions.githubusercontent.com" \
  --client-id-list "sts.amazonaws.com" \
  --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1" "1c58a3a8518e8759bf075b76b750d4f8d264fcd9"
```

---

## 3. Step 2: Create IAM Role for GitHub Actions (CD Pipeline)

### 3.1 Prepare Trust Policy
Update `deployment/aws/github-oidc-trust-policy.json` with your AWS Account ID and GitHub username/org:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GitHubOIDCAuth",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:<YOUR_GITHUB_USER>/CloudDeploy-AWS-CICD:*"
        }
      }
    }
  ]
}
```

### 3.2 Create IAM Role & Attach Least-Privilege Policy
```bash
# Create the role
aws iam create-role \
  --role-name CloudDeploy-GitHub-OIDC-Role \
  --assume-role-policy-document file://deployment/aws/github-oidc-trust-policy.json

# Attach the deployment permissions policy
aws iam put-role-policy \
  --role-name CloudDeploy-GitHub-OIDC-Role \
  --policy-name CloudDeployDeploymentPolicy \
  --policy-document file://deployment/aws/iam-policy.json
```
Save the returned Role ARN (e.g. `arn:aws:iam::123456789012:role/CloudDeploy-GitHub-OIDC-Role`).

---

## 4. Step 3: Create Amazon ECR Repository

Execute the repository setup script:
```bash
chmod +x deployment/scripts/ecr-setup.sh
./deployment/scripts/ecr-setup.sh clouddeploy us-east-1
```
This provisions:
- Repository: `clouddeploy`
- Server-side encryption: AES-256
- Scan on push: Enabled
- Lifecycle retention policy: Retains last 10 images

---

## 5. Step 4: Create EC2 IAM Instance Profile

The EC2 instance needs permissions to pull images from ECR and stream logs to CloudWatch.

```bash
# Create EC2 role
aws iam create-role \
  --role-name CloudDeploy-EC2-Instance-Role \
  --assume-role-policy-document file://deployment/aws/ec2-trust-policy.json

# Attach permissions
aws iam put-role-policy \
  --role-name CloudDeploy-EC2-Instance-Role \
  --policy-name CloudDeployEC2Policy \
  --policy-document file://deployment/aws/ec2-instance-policy.json

# Create instance profile and add role
aws iam create-instance-profile --instance-profile-name CloudDeploy-EC2-Profile
aws iam add-role-to-instance-profile \
  --instance-profile-name CloudDeploy-EC2-Profile \
  --role-name CloudDeploy-EC2-Instance-Role
```

---

## 6. Step 5: Launch the EC2 Deployment Server

### 6.1 Create Security Group
```bash
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text)

SG_ID=$(aws ec2 create-security-group \
  --group-name clouddeploy-sg \
  --description "Security group for CloudDeploy web server" \
  --vpc-id "$VPC_ID" \
  --query "GroupId" --output text)

# Allow HTTP Port 80 (Public)
aws ec2 authorize-security-group-ingress \
  --group-id "$SG_ID" \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0
```

### 6.2 Launch Instance with User Data
```bash
# Retrieve latest Ubuntu 24.04 AMI
AMI_ID=$(aws ssm get-parameters \
  --names /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
  --query "Parameters[0].Value" --output text)

INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type t3.micro \
  --iam-instance-profile Name=CloudDeploy-EC2-Profile \
  --security-group-ids "$SG_ID" \
  --user-data file://deployment/aws/ec2-user-data.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=clouddeploy-server}]' \
  --query "Instances[0].InstanceId" --output text)

echo "Launched EC2 instance: $INSTANCE_ID"
```

Wait ~2-3 minutes for the instance to initialize and for the user-data script to install Docker and Nginx.

---

## 7. Step 6: Configure GitHub Repository Secrets & Variables

In your GitHub repository, navigate to **Settings** > **Secrets and variables** > **Actions**:

### 7.1 Secrets
| Name | Description | Example Value |
|---|---|---|
| `AWS_ROLE_ARN` | The ARN of the GitHub OIDC role created in Step 2 | `arn:aws:iam::123456789012:role/CloudDeploy-GitHub-OIDC-Role` |

### 7.2 Variables
| Name | Description | Example Value |
|---|---|---|
| `AWS_REGION` | Target AWS region | `us-east-1` |
| `ECR_REPOSITORY` | Name of your ECR repository | `clouddeploy` |
| `EC2_INSTANCE_ID` | The instance ID launched in Step 5 | `i-0123456789abcdef0` |
| `APP_PUBLIC_URL` | Public IP or DNS of the EC2 instance | `http://54.210.12.34` |

---

## 8. Step 7: Trigger CI/CD Pipeline

1. Push your code to the `main` branch:
   ```bash
   git add .
   git commit -m "feat: complete CloudDeploy automated pipeline"
   git push origin main
   ```
2. GitHub Actions will trigger `CI Pipeline - Build & Test`:
   - Runs flake8 linting.
   - Executes Pytest test suite with code coverage.
   - Verifies Docker build.
3. Upon CI success, `CD Pipeline - Deploy to AWS` initiates:
   - Connects to AWS via OIDC.
   - Builds container and pushes to Amazon ECR tagged with the short commit SHA.
   - Dispatches deployment to the EC2 instance via AWS SSM.
   - Verifies `GET /health` returns HTTP 200.

---

## 9. Step 8: CloudWatch Observability & Alarms

To set up proactive monitoring:
```bash
# CPU Utilization Alarm (> 80% for 5 min)
aws cloudwatch put-metric-alarm \
  --alarm-name "CloudDeploy-EC2-HighCPU" \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=InstanceId,Value="$INSTANCE_ID" \
  --evaluation-periods 1

# System Status Check Alarm
aws cloudwatch put-metric-alarm \
  --alarm-name "CloudDeploy-EC2-StatusCheckFailed" \
  --metric-name StatusCheckFailed \
  --namespace AWS/EC2 \
  --statistic Maximum \
  --period 60 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --dimensions Name=InstanceId,Value="$INSTANCE_ID" \
  --evaluation-periods 1
```

---

## 10. Step 9: Zero-Lingering-Cost Teardown

When you are finished testing or demonstrating the project, run the cleanup script to terminate all resources:
```bash
chmod +x deployment/aws/cleanup.sh
./deployment/aws/cleanup.sh us-east-1
```
This terminates the EC2 instance, deletes the ECR repository, removes CloudWatch log groups, and deletes IAM roles, ensuring you incur **$0 ongoing charges**.
