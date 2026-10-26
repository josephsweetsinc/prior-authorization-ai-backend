# Dev Environment Configuration
# Note: This environment uses the default VPC to reduce costs and complexity

# Application Configuration
#
# Must be distinct from prod's domain (api.infopaai.com) - the EC2
# module requests a Let's Encrypt cert for this exact hostname via
# certbot's HTTP-01 challenge, which fails if DNS for it doesn't
# already point at this environment's own instance. Before running
# deploy-project.yml for dev, create a DNS A record for this
# subdomain pointing at the dev instance's public IP (available as
# the ec2_public_ip Terraform output after the instance exists - so
# provision once with an empty domain, point DNS at the resulting IP,
# then re-apply with this domain set, or reserve/assign the IP ahead
# of time if this account uses an Elastic IP for it).
domain        = "dev-api.infopaai.com"

# EC2 Configuration
instance_type = "t4g.small"
allowed_ports = ["22", "80", "443"]
