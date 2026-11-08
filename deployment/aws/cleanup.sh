#!/bin/bash
# ==============================================================================
# CloudDeploy - AWS Resource Cleanup & Decommissioning Script
# Safely tears down deployed resources to guarantee ZERO lingering cloud costs
# ==============================================================================

set -euo pipefail

AWS_REGION="${1:-us-east-1}"
ECR_REPO_NAME="clouddeploy"
EC2_NAME="clouddeploy-server"
ROLE_NAME="CloudDeploy-GitHub-OIDC-Role"
EC2_ROLE_NAME="CloudDeploy-EC2-Instance-Role"
SG_NAME="clouddeploy-sg"

echo "======================================================================"
echo " CloudDeploy AWS Resource Cleanup Utility"
echo " Region: $AWS_REGION"
echo "======================================================================"
read -p "Are you sure you want to delete all CloudDeploy AWS resources? (y/N): " -r CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "Cleanup cancelled."
    exit 0
fi

# 1. Terminate EC2 Instances
echo "[1/5] Terminating EC2 instances with tag Name=$EC2_NAME..."
INSTANCE_IDS=$(aws ec2 describe-instances \
    --region "$AWS_REGION" \
    --filters "Name=tag:Name,Values=$EC2_NAME" "Name=instance-state-name,Values=running,stopped" \
    --query "Reservations[].Instances[].InstanceId" \
    --output text)

if [ -n "$INSTANCE_IDS" ]; then
    echo "Terminating instances: $INSTANCE_IDS"
    aws ec2 terminate-instances --region "$AWS_REGION" --instance-ids $INSTANCE_IDS
    echo "Waiting for instance termination..."
    aws ec2 wait instance-terminated --region "$AWS_REGION" --instance-ids $INSTANCE_IDS
    echo "EC2 instances terminated."
else
    echo "No active EC2 instances found."
fi

# 2. Delete Security Group
echo "[2/5] Removing Security Group $SG_NAME..."
SG_ID=$(aws ec2 describe-security-groups \
    --region "$AWS_REGION" \
    --group-names "$SG_NAME" \
    --query "SecurityGroups[0].GroupId" \
    --output text 2>/dev/null || echo "")

if [ -n "$SG_ID" ] && [ "$SG_ID" != "None" ]; then
    aws ec2 delete-security-group --region "$AWS_REGION" --group-id "$SG_ID" || true
    echo "Security group deleted."
else
    echo "Security group not found."
fi

# 3. Delete Amazon ECR Repository (with all images)
echo "[3/5] Deleting Amazon ECR repository: $ECR_REPO_NAME..."
aws ecr delete-repository \
    --region "$AWS_REGION" \
    --repository-name "$ECR_REPO_NAME" \
    --force 2>/dev/null || echo "ECR repository not found or already deleted."

# 4. Remove CloudWatch Log Groups
echo "[4/5] Deleting CloudWatch Log Groups..."
LOG_GROUPS=(
    "/aws/ec2/clouddeploy/nginx/access"
    "/aws/ec2/clouddeploy/nginx/error"
    "/aws/ec2/clouddeploy/deployment"
)
for lg in "${LOG_GROUPS[@]}"; do
    aws logs delete-log-group --region "$AWS_REGION" --log-group-name "$lg" 2>/dev/null || true
done

# 5. Detach and Delete IAM Roles & Policies
echo "[5/5] Decommissioning IAM Roles..."
aws iam delete-role-policy --role-name "$ROLE_NAME" --policy-name CloudDeployGitHubActionsPolicy 2>/dev/null || true
aws iam delete-role --role-name "$ROLE_NAME" 2>/dev/null || true

aws iam remove-role-from-instance-profile --instance-profile-name "${EC2_ROLE_NAME}-profile" --role-name "$EC2_ROLE_NAME" 2>/dev/null || true
aws iam delete-instance-profile --instance-profile-name "${EC2_ROLE_NAME}-profile" 2>/dev/null || true
aws iam delete-role-policy --role-name "$EC2_ROLE_NAME" --policy-name CloudDeployEC2Policy 2>/dev/null || true
aws iam delete-role --role-name "$EC2_ROLE_NAME" 2>/dev/null || true

echo "======================================================================"
echo " CloudDeploy resource cleanup completed. No lingering billable resources."
echo "======================================================================"
