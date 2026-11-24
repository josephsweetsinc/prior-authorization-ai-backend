data "aws_vpc" "this" {
  id = var.vpc_id
}
# Get the current AWS region
data "aws_region" "current" {}

# Get current caller identity for reference
data "aws_caller_identity" "current" {}

# Canonical's Ubuntu 24.04 LTS AMI
data "aws_ami" "ubuntu_24_04" {
  most_recent = true
  owners      = ["099720109477"] # Canonical's AWS account ID

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# Local values
locals {
  ubuntu_ami     = data.aws_ami.ubuntu_24_04.id
  ubuntu_version = "24.04 LTS (Noble)"
}

module "key_pair" {
  source = "terraform-aws-modules/key-pair/aws"

  key_name   = "${var.name}-key"
  public_key = var.SSH_KEY_PUB
}

module "ec2_instance" {
  source = "terraform-aws-modules/ec2-instance/aws"

  name  = var.name
  count = 1

  ami_ssm_parameter           = "/aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id"
  instance_type               = var.type
  key_name                    = module.key_pair.key_pair_name
  vpc_security_group_ids      = [resource.aws_security_group.this.id]
  subnet_id                   = element(tolist(var.subnet_ids), 0)
  associate_public_ip_address = true
  monitoring                  = true
  user_data_replace_on_change = true
  user_data                   = <<-EOT
    #!/bin/bash

    # Install docker, nginx, git

    sudo apt-get update
    sudo apt-get install ca-certificates curl -y
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update

    sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin nginx git certbot htop fail2ban -y
    sudo groupadd docker
    sudo usermod -aG docker ubuntu

    # Enable docker to start with system

    sudo systemctl enable docker.service
    sudo systemctl enable containerd.service
    sudo systemctl start docker

    # Auto-block IPs that repeatedly fail SSH login, since port 22 has
    # to stay open to 0.0.0.0/0 for both admin access and this
    # project's own GitHub Actions deploy workflows (which connect
    # from GitHub's shared, non-fixed runner IP ranges, so it can't
    # be restricted to a single allowed source instead).

    echo '[sshd]
    enabled = true
    port = ssh
    filter = sshd
    logpath = /var/log/auth.log
    maxretry = 5
    bantime = 1h
    findtime = 10m' | sudo tee /etc/fail2ban/jail.local > /dev/null
    sudo systemctl enable fail2ban
    sudo systemctl restart fail2ban

    # Set up ssh access to git account

    cd /home/ubuntu/
    sudo echo "${var.SSH_KEY_PUB}" >> ./.ssh/authorized_keys
    echo "${var.SSH_KEY}" > ./.ssh/id_rsa
    echo "${var.SSH_KEY_PUB}" > ./.ssh/id_rsa.pub
    sudo chmod 600 ./.ssh/id_rsa
    sudo  chown -R ubuntu:ubuntu ./.ssh

    echo 'Host github.com
      HostName github.com
      User git
      IdentityFile ~/.ssh/id_rsa
      IdentitiesOnly yes' > ./.ssh/config

    sudo -u ubuntu ssh -o StrictHostKeyChecking=no -T git@github.com

    # Pull project repo

    sudo -u ubuntu git clone git@github.com:${var.FULL_REPO_NAME}
    cd ./${var.REPO_NAME}
    # sudo -u ubuntu git checkout main
    sudo docker compose up -d

    # Download the certificates

    if [ -n "${var.domain}" ]; then
      sudo systemctl stop nginx; sudo  certbot certonly --standalone -d ${var.domain} --staple-ocsp -m example@gmail.com --agree-tos; sudo systemctl restart nginx

      # Add cronjob for certificates renewal

      echo "0 12 * * * sudo systemctl stop nginx; /usr/bin/certbot renew --quiet; sudo systemctl restart nginx" | crontab -
    fi

    # Add nginx .conf files for api

    sudo chmod 777 /etc/nginx/conf.d/

    sudo rm /etc/nginx/sites-enabled/default

    if [ -n "${var.domain}" ]; then
      echo 'server {
    listen 80 default_server;
    server_name localhost;
    return 301 https://$host$request_uri;
    }

    server {
      listen 443 ssl;
      server_name ${var.domain};
      ssl_certificate /etc/letsencrypt/live/${var.domain}/fullchain.pem;
      ssl_certificate_key /etc/letsencrypt/live/${var.domain}/privkey.pem;

      types_hash_max_size 10240;
      client_max_body_size 10M;

      location / {
          proxy_pass http://127.0.0.1:3100/;
          proxy_set_header Host $host;
          proxy_set_header X-Real-IP $remote_addr;
          proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
          proxy_set_header X-Forwarded-Proto $scheme;

          # Optional Timeouts
          send_timeout 5m;
          proxy_read_timeout 240;
          proxy_send_timeout 240;
          proxy_connect_timeout 240;

          # Optional Headers
          # add_header Access-Control-Allow-Origin * always;
          # add_header Access-Control-Allow-Headers * always;

          proxy_cache_bypass $cookie_session;
          proxy_no_cache $cookie_session;
          proxy_buffers 32 4k;
        }
        location /Prod/api/v1/websocket/ {
              proxy_pass http://127.0.0.1:3100/Prod/api/v1/websocket/;
              proxy_http_version 1.1;
              proxy_set_header Upgrade $http_upgrade;
              proxy_set_header Connection "upgrade";
              proxy_set_header Host $host;
              proxy_set_header X-Real-IP $remote_addr;
              proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
              proxy_set_header X-Forwarded-Proto $scheme;
              proxy_set_header Authorization $http_authorization;

              # WebSocket specific timeouts
              proxy_read_timeout 86400;
              proxy_send_timeout 86400;
              proxy_connect_timeout 86400;
          }
      }' > /etc/nginx/conf.d/app-api.conf
    else
        echo 'server {
    listen 80 default_server;
    server_name localhost;
    # return 301 https://$host$request_uri;
    # }

    # server {
    #   listen 443 ssl;
    #   server_name ${var.domain};
    #   ssl_certificate /etc/letsencrypt/live/${var.domain}/fullchain.pem;
    #   ssl_certificate_key /etc/letsencrypt/live/${var.domain}/privkey.pem;

    types_hash_max_size 10240;
    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:3100/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Optional Timeouts
        send_timeout 5m;
        proxy_read_timeout 240;
        proxy_send_timeout 240;
        proxy_connect_timeout 240;

        # Optional Headers
        # add_header Access-Control-Allow-Origin * always;
        # add_header Access-Control-Allow-Headers * always;

        proxy_cache_bypass $cookie_session;
        proxy_no_cache $cookie_session;
        proxy_buffers 32 4k;
      }
      location /Prod/api/v1/websocket/ {
            proxy_pass http://127.0.0.1:3100/Prod/api/v1/websocket/;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Authorization $http_authorization;

            # WebSocket specific timeouts
            proxy_read_timeout 86400;
            proxy_send_timeout 86400;
            proxy_connect_timeout 86400;
        }
    }' > /etc/nginx/conf.d/app-api.conf
    fi

    sudo systemctl restart nginx

    # sudo -u ubuntu newgrp docker
  EOT

  root_block_device = {
    size = 30
    # tags = {
    #   Name = "my-root-block"
    # }
  }
  enable_volume_tags = true


  tags = merge({
    Terraform = "1"
  }, var.tags)
}


resource "aws_security_group" "this" {
  name   = "${var.name}-ec2-sg"
  vpc_id = var.vpc_id
  tags = merge({
    Terraform = "1"
  }, var.tags)
}

resource "aws_security_group_rule" "egress" {
  security_group_id = aws_security_group.this.id
  from_port         = 0
  to_port           = 65535
  type              = "egress"
  protocol          = "TCP"
  cidr_blocks       = ["0.0.0.0/0"]
}

# locals {
#   ports = toset(["22", "80", "443", "8080", "65402", "9443"])
# }

resource "aws_security_group_rule" "ingress" {
  for_each          = toset(var.ports)
  security_group_id = aws_security_group.this.id
  from_port         = each.value
  to_port           = each.value
  protocol          = "TCP"
  type              = "ingress"
  cidr_blocks       = ["0.0.0.0/0"]
}

resource "aws_eip" "ip" {
  instance = module.ec2_instance[0].id
  domain   = "vpc"
  tags = merge({
    Terraform = "1"
  }, var.tags)
}

# Tag the instance ENI (Elastic Network Interface)
resource "aws_ec2_tag" "eni" {
  for_each = merge({
    Terraform = "1"
  }, var.tags)

  resource_id = module.ec2_instance[0].primary_network_interface_id
  key         = each.key
  value       = each.value
}
