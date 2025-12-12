# Root folder
$root = "cs3-nca"
New-Item -ItemType Directory -Path $root -Force | Out-Null

# Subfolders
$folders = @(
    "terraform",
    "k8s",
    "app/backend/utils",
    "app/backend",
    "app/worker",
    "app/frontend/src",
    "app/frontend"
)

foreach ($folder in $folders) {
    $path = Join-Path $root $folder
    New-Item -ItemType Directory -Path $path -Force | Out-Null
}

# Files to create (empty)
$files = @(
    "terraform/main.tf",
    "terraform/provider.tf",
    "terraform/variables.tf",
    "terraform/vpc.tf",
    "terraform/eks.tf",
    "terraform/irsa.tf",
    "terraform/dynamodb.tf",
    "terraform/sqs.tf",
    "terraform/eventbridge.tf",
    "terraform/outputs.tf",

    "k8s/backend-deployment.yaml",
    "k8s/backend-service.yaml",
    "k8s/frontend-deployment.yaml",
    "k8s/frontend-service.yaml",
    "k8s/ingress.yaml",
    "k8s/worker-job.yaml",
    "k8s/serviceaccount-backend.yaml",
    "k8s/serviceaccount-worker.yaml",
    "k8s/rbac.yaml",

    "app/backend/main.py",
    "app/backend/requirements.txt",
    "app/backend/Dockerfile",
    "app/backend/utils/dynamodb.py",

    "app/worker/worker.py",
    "app/worker/requirements.txt",
    "app/worker/Dockerfile",

    "app/frontend/package.json",
    "app/frontend/Dockerfile",
    "app/frontend/src/App.jsx",
    "app/frontend/src/api.js",

    "README.md"
)

foreach ($file in $files) {
    $path = Join-Path $root $file
    New-Item -ItemType File -Path $path -Force | Out-Null
}

Write-Host "Structuur succesvol aangemaakt in map: $root"
