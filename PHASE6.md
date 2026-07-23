# Phase 6 — Cloud Infrastructure (AWS + Terraform)

A beginner's step-by-step guide for someone who has **never touched AWS or Terraform**.

**Scope of this guide:** stand up a real cloud Postgres database (RDS) and point the
existing local pipeline at it. That single milestone teaches ~80% of Terraform's core
loop. The Lambda + EventBridge scheduling piece (running snapshots in the cloud on a
**4×/day** schedule, `rate(6 hours)`) is **Phase 6b** — a separate, later session.

**Key fact that makes this easy:** `src/db.py` calls `psycopg.connect()` with no
arguments, so it reads the standard libpq env vars (`PGHOST`, `PGPORT`, ...). Moving the
database to the cloud is therefore almost **zero code change** — just repoint those vars.

---

## Part 0 — One-time account & tool setup

### Step 1: Create an AWS account
https://aws.amazon.com/ → "Create an AWS Account." Needs a credit card (free tier covers
this). ~10 min.

### Step 2: Set a budget alarm FIRST (before creating anything)
Your safety net. In the AWS Console:
- Search → **Billing and Cost Management** → **Budgets** → **Create budget**
- Choose **Zero spend budget** (or a $1 budget) → enter your email → Create.

Do this before creating a single resource.

### Step 3: Create a login user (don't use the root account)
- Console search → **IAM** → **Users** → **Create user**
- Name it `mycpi-admin`
- Permissions → **Attach policies directly** → check **AdministratorAccess** (fine for a
  solo learning account) → Create.

### Step 4: Create access keys (so Terraform can log in as you)
- IAM → Users → `mycpi-admin` → **Security credentials** tab → **Create access key**
- Choose **Command Line Interface (CLI)** → Create.
- Copy the **Access key ID** and **Secret access key** now — the secret is shown only once.

### Step 5: Install the two tools
```bash
# AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscli.zip"
unzip awscli.zip && sudo ./aws/install
aws --version

# Terraform (via HashiCorp's apt repo)
wget -O - https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform
terraform --version
```

### Step 6: Log the CLI in
```bash
aws configure
```
Paste your Access key ID + Secret access key, region `us-east-1`, output `json`. Verify:
```bash
aws sts get-caller-identity   # should print your account/user
```

✅ **Checkpoint:** if that command shows your account, your machine can talk to AWS.

---

## Part 1 — Build cloud Postgres with Terraform

Create a folder `infra/` in the repo. Make **5 small files** in it.

### Step 7: `infra/main.tf` — which cloud, which region
```hcl
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = "us-east-1"
}
```

### Step 8: `infra/variables.tf` — inputs you'll fill in
```hcl
variable "db_password" {
  type      = string
  sensitive = true
}

variable "my_ip" {
  type        = string
  description = "Your public IP in CIDR form, e.g. 1.2.3.4/32"
}
```

### Step 9: `infra/rds.tf` — the database + who can reach it
```hcl
# Firewall: allow Postgres (5432) only from your IP
resource "aws_security_group" "rds" {
  name        = "mycpi-rds"
  description = "Allow Postgres from my IP"

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.my_ip]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# The managed Postgres instance
resource "aws_db_instance" "mycpi" {
  identifier             = "mycpi"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = "db.t4g.micro"
  allocated_storage      = 20
  db_name                = "mycpi"
  username               = "mycpi_admin"
  password               = var.db_password
  publicly_accessible    = true
  skip_final_snapshot    = true
  vpc_security_group_ids = [aws_security_group.rds.id]
}
```

### Step 10: `infra/outputs.tf` — print the address after building
```hcl
output "rds_endpoint" {
  value = aws_db_instance.mycpi.endpoint
}
```

### Step 11: `infra/terraform.tfvars` — your actual secret values (never commit this)
```hcl
db_password = "pick-a-strong-password-here"
my_ip       = "YOUR.IP.HERE/32"
```
Get your IP with `curl -s ifconfig.me`, then append `/32`.

### Step 12: Keep secrets out of git
Add to `.gitignore`:
```
infra/.terraform/
infra/*.tfstate*
infra/terraform.tfvars
```
⚠️ `.tfstate` and `.tfvars` contain your DB password in plaintext.

---

## Part 2 — Run it

```bash
cd infra
terraform init      # downloads the AWS plugin (one time)
terraform plan      # PREVIEW — should say "3 to add, 0 to change, 0 to destroy"
terraform apply     # type 'yes' — RDS takes ~5-10 min to spin up
```

It prints `rds_endpoint = "mycpi.xxxx.us-east-1.rds.amazonaws.com:5432"`. That's your
cloud database.

### Step 13: Load the schema
```bash
# from project root; host part of the endpoint (no :5432)
psql -h mycpi.xxxx.us-east-1.rds.amazonaws.com -U mycpi_admin -d mycpi -f init.sql
```

### Step 14: Point the local app at the cloud DB
Edit `.env` so the `PG*` vars target RDS:
```
PGHOST=mycpi.xxxx.us-east-1.rds.amazonaws.com
PGPORT=5432
PGUSER=mycpi_admin
PGPASSWORD=the-password-from-tfvars
PGDATABASE=mycpi
```
Then run the existing pipeline unchanged:
```bash
python src/main.py
```

✅ **Milestone:** a snapshot landed in a database running in AWS, provisioned entirely
from code.

---

## Part 3 — The most important habit: tear it down

When done experimenting for the day:
```bash
cd infra
terraform destroy   # type 'yes' — deletes everything, stops all billing
```
`terraform apply` rebuilds it in minutes next time. An idle RDS instance is the classic
$15 surprise — get comfortable destroying.

---

## Phase 6b (later) — Lambda + EventBridge

Once RDS feels comfortable, move the snapshot job off the laptop into the cloud:

- **Lambda** runs `main.py` (refactor its body into a `run()` function + a thin
  `lambda_handler.py` wrapper).
- **EventBridge Scheduler** triggers it on a **4×/day** cadence: `rate(6 hours)`.
- **Secrets Manager** holds Kroger + DB creds instead of plaintext env vars.
- **Packaging gotcha:** `psycopg` has compiled parts — package Lambda as a **container
  image** (Dockerfile → ECR → Lambda) rather than a zip. This is the fiddliest step and
  deserves its own walkthrough.
