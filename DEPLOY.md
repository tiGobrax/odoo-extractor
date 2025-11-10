# 🚀 Guia de Deploy no Amazon EKS

Este documento contém instruções específicas para deploy do **Odoo Extractor** no **Amazon Elastic Kubernetes Service (EKS)**.

## 📋 Pré-requisitos

- AWS CLI configurado com credenciais apropriadas
- `kubectl` instalado e configurado para o cluster EKS
- `eksctl` instalado (opcional, para gerenciar clusters)
- Cluster EKS criado e configurado
- Permissões IAM adequadas para:
  - ECR (push/pull de imagens)
  - EKS (deploy de workloads)
  - Secrets Manager (se usar para secrets)

## 🐳 1. Build e Push da Imagem para ECR

### 1.1 Criar Repositório ECR (se não existir)

```bash
aws ecr create-repository \
  --repository-name odoo-extractor \
  --region us-east-1 \
  --image-scanning-configuration scanOnPush=true
```

### 1.2 Autenticar no ECR

```bash
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
```

### 1.3 Build, Tag e Push da Imagem

```bash
# Build da imagem
docker build -t odoo-extractor:latest .

# Tag para ECR
docker tag odoo-extractor:latest \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/odoo-extractor:latest

docker tag odoo-extractor:latest \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/odoo-extractor:$(git rev-parse --short HEAD)

# Push para ECR
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/odoo-extractor:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/odoo-extractor:$(git rev-parse --short HEAD)
```

## 🔐 2. Configuração de Secrets

### Opção A: AWS Secrets Manager (Recomendado)

#### 2.1 Criar Secret no AWS Secrets Manager

```bash
aws secretsmanager create-secret \
  --name odoo-extractor/secrets \
  --description "Secrets para Odoo Extractor" \
  --secret-string '{
    "ODOO_URL": "https://seu-dominio.odoo.com",
    "ODOO_DB": "nome-do-banco",
    "ODOO_USERNAME": "usuario@email.com",
    "ODOO_PASSWORD": "api-key-ou-senha"
  }' \
  --region us-east-1
```

#### 2.2 Instalar External Secrets Operator (Opcional)

Para sincronizar automaticamente Secrets Manager com Kubernetes:

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets -n external-secrets-system --create-namespace
```

#### 2.3 Criar ExternalSecret (se usar External Secrets Operator)

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: odoo-extractor-secrets
  namespace: default
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: SecretStore
  target:
    name: odoo-secrets
    creationPolicy: Owner
  data:
  - secretKey: ODOO_URL
    remoteRef:
      key: odoo-extractor/secrets
      property: ODOO_URL
  - secretKey: ODOO_DB
    remoteRef:
      key: odoo-extractor/secrets
      property: ODOO_DB
  - secretKey: ODOO_USERNAME
    remoteRef:
      key: odoo-extractor/secrets
      property: ODOO_USERNAME
  - secretKey: ODOO_PASSWORD
    remoteRef:
      key: odoo-extractor/secrets
      property: ODOO_PASSWORD
```

### Opção B: Kubernetes Secrets (Alternativa)

```bash
kubectl create secret generic odoo-secrets \
  --from-literal=ODOO_URL='https://seu-dominio.odoo.com' \
  --from-literal=ODOO_DB='nome-do-banco' \
  --from-literal=ODOO_USERNAME='usuario@email.com' \
  --from-literal=ODOO_PASSWORD='api-key-ou-senha' \
  --namespace default
```

## 📦 3. Configuração de Namespace

```bash
kubectl create namespace odoo-extractor
```

Ou usando YAML:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: odoo-extractor
```

## 💾 4. Configuração de Storage (EBS)

### 4.1 Criar StorageClass (se necessário)

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: ebs-sc
provisioner: ebs.csi.aws.com
volumeBindingMode: WaitForFirstConsumer
parameters:
  type: gp3
  fsType: ext4
allowVolumeExpansion: true
```

### 4.2 Criar PersistentVolumeClaim

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: odoo-data-pvc
  namespace: odoo-extractor
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: ebs-sc
  resources:
    requests:
      storage: 20Gi
```

## 🚀 5. Deploy da Aplicação

### 5.1 Deployment para Execução Contínua

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: odoo-extractor
  namespace: odoo-extractor
  labels:
    app: odoo-extractor
spec:
  replicas: 1
  selector:
    matchLabels:
      app: odoo-extractor
  template:
    metadata:
      labels:
        app: odoo-extractor
    spec:
      serviceAccountName: odoo-extractor-sa
      containers:
      - name: odoo-extractor
        image: <AWS_ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/odoo-extractor:latest
        imagePullPolicy: Always
        env:
        - name: ODOO_URL
          valueFrom:
            secretKeyRef:
              name: odoo-secrets
              key: ODOO_URL
        - name: ODOO_DB
          valueFrom:
            secretKeyRef:
              name: odoo-secrets
              key: ODOO_DB
        - name: ODOO_USERNAME
          valueFrom:
            secretKeyRef:
              name: odoo-secrets
              key: ODOO_USERNAME
        - name: ODOO_PASSWORD
          valueFrom:
            secretKeyRef:
              name: odoo-secrets
              key: ODOO_PASSWORD
        - name: ODOO_MODEL
          value: "res.partner"
        volumeMounts:
        - name: data-volume
          mountPath: /app/data
        resources:
          limits:
            memory: "2Gi"
            cpu: "2"
          requests:
            memory: "512Mi"
            cpu: "0.5"
        livenessProbe:
          exec:
            command:
            - python
            - -c
            - "import sys; sys.exit(0)"
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
        readinessProbe:
          exec:
            command:
            - python
            - -c
            - "import sys; sys.exit(0)"
          initialDelaySeconds: 10
          periodSeconds: 5
      volumes:
      - name: data-volume
        persistentVolumeClaim:
          claimName: odoo-data-pvc
```

### 5.2 Job para Execução Única/Agendada (Recomendado)

Para extrações agendadas ou únicas, use Kubernetes Jobs:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: odoo-extractor-job
  namespace: odoo-extractor
spec:
  ttlSecondsAfterFinished: 86400  # Remove job após 24h
  backoffLimit: 2
  template:
    spec:
      serviceAccountName: odoo-extractor-sa
      restartPolicy: Never
      containers:
      - name: odoo-extractor
        image: <AWS_ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/odoo-extractor:latest
        imagePullPolicy: Always
        env:
        - name: ODOO_URL
          valueFrom:
            secretKeyRef:
              name: odoo-secrets
              key: ODOO_URL
        - name: ODOO_DB
          valueFrom:
            secretKeyRef:
              name: odoo-secrets
              key: ODOO_DB
        - name: ODOO_USERNAME
          valueFrom:
            secretKeyRef:
              name: odoo-secrets
              key: ODOO_USERNAME
        - name: ODOO_PASSWORD
          valueFrom:
            secretKeyRef:
              name: odoo-secrets
              key: ODOO_PASSWORD
        - name: ODOO_MODEL
          value: "res.partner"
        volumeMounts:
        - name: data-volume
          mountPath: /app/data
        resources:
          limits:
            memory: "2Gi"
            cpu: "2"
          requests:
            memory: "512Mi"
            cpu: "0.5"
      volumes:
      - name: data-volume
        persistentVolumeClaim:
          claimName: odoo-data-pvc
```

### 5.3 CronJob para Execução Agendada

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: odoo-extractor-cron
  namespace: odoo-extractor
spec:
  schedule: "0 2 * * *"  # Executa diariamente às 2h
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 1
  jobTemplate:
    spec:
      ttlSecondsAfterFinished: 86400
      template:
        spec:
          serviceAccountName: odoo-extractor-sa
          restartPolicy: Never
          containers:
          - name: odoo-extractor
            image: <AWS_ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/odoo-extractor:latest
            imagePullPolicy: Always
            env:
            - name: ODOO_URL
              valueFrom:
                secretKeyRef:
                  name: odoo-secrets
                  key: ODOO_URL
            - name: ODOO_DB
              valueFrom:
                secretKeyRef:
                  name: odoo-secrets
                  key: ODOO_DB
            - name: ODOO_USERNAME
              valueFrom:
                secretKeyRef:
                  name: odoo-secrets
                  key: ODOO_USERNAME
            - name: ODOO_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: odoo-secrets
                  key: ODOO_PASSWORD
            - name: ODOO_MODEL
              value: "res.partner"
            volumeMounts:
            - name: data-volume
              mountPath: /app/data
            resources:
              limits:
                memory: "2Gi"
                cpu: "2"
              requests:
                memory: "512Mi"
                cpu: "0.5"
          volumes:
          - name: data-volume
            persistentVolumeClaim:
              claimName: odoo-data-pvc
```

## 🔑 6. Configuração de IAM (IRSA)

### 6.1 Criar Service Account com IRSA (se usar Secrets Manager)

```bash
eksctl create iamserviceaccount \
  --name odoo-extractor-sa \
  --namespace odoo-extractor \
  --cluster <cluster-name> \
  --attach-policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite \
  --approve \
  --override-existing-serviceaccounts
```

Ou manualmente:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: odoo-extractor-sa
  namespace: odoo-extractor
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::<ACCOUNT_ID>:role/odoo-extractor-role
```

### 6.2 Criar IAM Role e Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:<REGION>:<ACCOUNT_ID>:secret:odoo-extractor/secrets-*"
    }
  ]
}
```

## 📊 7. Configuração de Logs (CloudWatch)

### 7.1 Instalar CloudWatch Agent (se necessário)

```bash
kubectl apply -f https://raw.githubusercontent.com/aws-samples/amazon-cloudwatch-container-insights/latest/k8s-deployment-manifests/fluent-bit/fluent-bit.yaml
```

### 7.2 Logs Automáticos

Os logs do container (stdout/stderr) são automaticamente coletados pelo CloudWatch Logs através do Fluent Bit do EKS.

Para visualizar:

```bash
aws logs tail /aws/eks/<cluster-name>/cluster --follow
```

Ou no console AWS: **CloudWatch > Log groups > /aws/eks/<cluster-name>/cluster**

## 📈 8. Monitoramento e Métricas

### 8.1 CloudWatch Container Insights

Ative Container Insights no cluster:

```bash
aws eks update-cluster-config \
  --name <cluster-name> \
  --logging '{"enable":["api","audit","authenticator","controllerManager","scheduler"]}'
```

### 8.2 Prometheus (Opcional)

Se usar Prometheus no cluster:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: odoo-extractor-metrics
  namespace: odoo-extractor
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8080"
spec:
  selector:
    app: odoo-extractor
  ports:
  - port: 8080
    name: metrics
```

## 🔄 9. CI/CD com GitHub Actions

```yaml
name: Build and Deploy to EKS

on:
  push:
    branches: [main]

env:
  AWS_REGION: us-east-1
  ECR_REPOSITORY: odoo-extractor
  EKS_CLUSTER: odoo-extractor-cluster

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}
      
      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v1
      
      - name: Build, tag, and push image to Amazon ECR
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
          docker tag $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG $ECR_REGISTRY/$ECR_REPOSITORY:latest
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:latest

  deploy:
    needs: build-and-push
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}
      
      - name: Update kubeconfig
        run: |
          aws eks update-kubeconfig --name ${{ env.EKS_CLUSTER }} --region ${{ env.AWS_REGION }}
      
      - name: Deploy to EKS
        run: |
          kubectl set image deployment/odoo-extractor \
            odoo-extractor=${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_REPOSITORY }}:${{ github.sha }} \
            -n odoo-extractor
          kubectl rollout status deployment/odoo-extractor -n odoo-extractor
```

## 📝 10. Checklist de Deploy no EKS

- [ ] Cluster EKS criado e configurado
- [ ] `kubectl` configurado para o cluster
- [ ] Repositório ECR criado
- [ ] Imagem Docker buildada e enviada para ECR
- [ ] Secrets configurados (Secrets Manager ou Kubernetes Secrets)
- [ ] Namespace criado
- [ ] StorageClass e PVC configurados (se necessário)
- [ ] Service Account criado (com IRSA se usar Secrets Manager)
- [ ] Deployment/Job/CronJob aplicado
- [ ] CloudWatch Logs configurado
- [ ] Health checks funcionando
- [ ] Teste de execução bem-sucedido

## 🆘 11. Troubleshooting

### Verificar Status do Pod

```bash
kubectl get pods -n odoo-extractor
kubectl describe pod <pod-name> -n odoo-extractor
```

### Ver Logs

```bash
kubectl logs -f <pod-name> -n odoo-extractor
```

### Verificar Secrets

```bash
kubectl get secrets -n odoo-extractor
kubectl describe secret odoo-secrets -n odoo-extractor
```

### Verificar PVC

```bash
kubectl get pvc -n odoo-extractor
kubectl describe pvc odoo-data-pvc -n odoo-extractor
```

### Verificar Service Account

```bash
kubectl get serviceaccount -n odoo-extractor
kubectl describe serviceaccount odoo-extractor-sa -n odoo-extractor
```

### Executar Shell no Pod

```bash
kubectl exec -it <pod-name> -n odoo-extractor -- /bin/bash
```

### Verificar Variáveis de Ambiente

```bash
kubectl exec <pod-name> -n odoo-extractor -- env | grep ODOO
```

### Verificar Imagem no ECR

```bash
aws ecr describe-images \
  --repository-name odoo-extractor \
  --region us-east-1
```

### Ver Logs no CloudWatch

```bash
aws logs tail /aws/eks/<cluster-name>/cluster --follow --format short
```

## 🔒 12. Segurança

### Boas Práticas Implementadas

- ✅ Container roda como usuário não-root
- ✅ Multi-stage build para reduzir tamanho da imagem
- ✅ Secrets gerenciados via AWS Secrets Manager ou Kubernetes Secrets
- ✅ IRSA para acesso seguro a serviços AWS
- ✅ Network Policies (configure conforme necessário)
- ✅ Pod Security Standards

### Recomendações Adicionais

1. **Use AWS Secrets Manager** ao invés de Kubernetes Secrets para produção
2. **Habilite Encryption at Rest** para EBS volumes
3. **Use Network Policies** para restringir tráfego de rede
4. **Scan de vulnerabilidades** da imagem no ECR
5. **Use Pod Security Standards** do Kubernetes
6. **Rotacione secrets** regularmente
7. **Use IAM Roles** (IRSA) ao invés de credenciais estáticas

## 📚 Referências

- [Amazon EKS Documentation](https://docs.aws.amazon.com/eks/)
- [EKS Best Practices](https://aws.github.io/aws-eks-best-practices/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [AWS ECR Documentation](https://docs.aws.amazon.com/ecr/)
