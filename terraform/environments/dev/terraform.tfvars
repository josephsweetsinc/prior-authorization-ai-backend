# Dev Environment Configuration
# Note: This environment uses the default VPC to reduce costs and complexity

# Application Configuration
#
# Intentionally blank for the first provisioning pass: the instance's
# public IP isn't known until after it exists, so DNS for
# dev-api.infopaai.com can't point at it yet, and certbot's HTTP-01
# challenge would just fail on first boot. The box comes up on plain
# HTTP for now. Once provisioned, point a DNS A record for
# dev-api.infopaai.com at the ec2_public_ip Terraform output, then set
# domain back to "dev-api.infopaai.com" here and either re-apply
# (replaces the instance - fine once DNS already points at a
# reserved/known IP) or run certbot by hand on the existing box.
domain        = ""

# EC2 Configuration
instance_type = "t4g.small"
allowed_ports = ["22", "80", "443"]
