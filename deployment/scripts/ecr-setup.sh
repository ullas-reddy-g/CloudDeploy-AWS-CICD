#!/bin/bash
# ==============================================================================
# CloudDeploy - Amazon ECR Repository Setup & Lifecycle Policy Provisioner
# ==============================================================================

set -euo pipefail

REPOSITORY_NAME="${1:-clouddeploy}"
AWS_REGION="${2:-us-east-1}"

echo "======================================================================"
echo " Creating Amazon ECR Repository: $REPOSITORY_NAME in $AWS_REGION"
echo "======================================================================"

# 1. Create Repository with Scan-on-Push
if aws ecr describe-repositories --repository-names "$REPOSITORY_NAME" --region "$AWS_REGION" &>/dev/null; then
    echo "ECR repository '$REPOSITORY_NAME' already exists."
else
    echo "Creating repository '$REPOSITORY_NAME'..."
    aws ecr create-repository \
        --repository-name "$REPOSITORY_NAME" \
        --image-scanning-configuration scanOnPush=true \
        --encryption-configuration encryptionType=AES256 \
        --region "$AWS_REGION"
    echo "Repository created successfully."
fi

# 2. Apply Lifecycle Policy to prevent storage bloat (keep last 10 images)
echo "Applying image lifecycle retention policy (keep 10 latest images)..."
cat << 'EOF' > /tmp/ecr-lifecycle-policy.json
{
  "rules": [
    {
      "rulePriority": 1,
      "description": "Retain only the last 10 tagged deployment images",
      "selection": {
        "tagStatus": "any",
        "countType": "imageCountMoreThan",
        "countNumber": 10
      },
      "action": {
        "type": "expire"
      }
    }
  ]
}
EOF

aws ecr put-lifecycle-policy \
    --repository-name "$REPOSITORY_NAME" \
    --lifecycle-policy-text file:///tmp/ecr-lifecycle-policy.json \
    --region "$AWS_REGION"

rm -f /tmp/ecr-lifecycle-policy.json

echo "ECR setup completed. URI: $(aws ecr describe-repositories --repository-names "$REPOSITORY_NAME" --region "$AWS_REGION" --query "repositories[0].repositoryUri" --output text)"
