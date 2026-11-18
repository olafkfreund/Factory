# AWS reference template: App Runner + private RDS Postgres + ElastiCache Redis.
# Validate before use; this template is not deployed by CI or the showcase.
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.0" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
}
provider "aws" {
  region = var.region
  default_tags {
    tags = {
      factory-ephemeral = "true"
      managed-by        = "factory"
    }
  }
}
variable "region" {
  type    = string
  default = "eu-west-2"
}
variable "image" {
  type = string # ECR image ref built by CI
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "connector" {
  name   = "factory-ttt-connector"
  vpc_id = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "data" {
  name   = "factory-ttt-data"
  vpc_id = data.aws_vpc.default.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.connector.id]
  }

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.connector.id]
  }
}

resource "aws_db_subnet_group" "pg" {
  name       = "factory-ttt-pg"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_elasticache_subnet_group" "redis" {
  name       = "factory-ttt-redis"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_apprunner_vpc_connector" "app" {
  vpc_connector_name = "factory-ttt-connector"
  subnets            = data.aws_subnets.default.ids
  security_groups    = [aws_security_group.connector.id]
}

resource "aws_iam_role" "app_runner_ecr" {
  name = "factory-ttt-ecr-access"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "build.apprunner.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "app_runner_ecr" {
  role       = aws_iam_role.app_runner_ecr.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

resource "random_password" "db" {
  length  = 20
  special = false
}

resource "aws_db_instance" "pg" {
  identifier             = "factory-ttt-pg"
  engine                 = "postgres"
  engine_version         = "15"
  instance_class         = "db.t3.micro"
  allocated_storage      = 20
  db_name                = "ttt"
  username               = "ttt"
  password               = random_password.db.result
  skip_final_snapshot    = true
  publicly_accessible    = false
  db_subnet_group_name   = aws_db_subnet_group.pg.name
  vpc_security_group_ids = [aws_security_group.data.id]
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "factory-ttt-redis"
  engine               = "redis"
  node_type            = "cache.t3.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  subnet_group_name    = aws_elasticache_subnet_group.redis.name
  security_group_ids   = [aws_security_group.data.id]
}

resource "aws_apprunner_service" "app" {
  service_name = "factory-ttt-app"
  source_configuration {
    authentication_configuration {
      access_role_arn = aws_iam_role.app_runner_ecr.arn
    }
    image_repository {
      image_identifier      = var.image
      image_repository_type = "ECR"
      image_configuration {
        port = "8080"
        runtime_environment_variables = {
          DATABASE_URL = "postgresql://ttt:${random_password.db.result}@${aws_db_instance.pg.address}:5432/ttt"
          REDIS_HOST   = aws_elasticache_cluster.redis.cache_nodes[0].address
          REDIS_PORT   = "6379"
        }
      }
    }
  }
  network_configuration {
    egress_configuration {
      egress_type       = "VPC"
      vpc_connector_arn = aws_apprunner_vpc_connector.app.arn
    }
  }
  depends_on = [aws_iam_role_policy_attachment.app_runner_ecr]
}
output "url" { value = "https://${aws_apprunner_service.app.service_url}" }
