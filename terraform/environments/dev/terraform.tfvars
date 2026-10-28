# Dev Environment Configuration
# Note: This environment uses the default VPC to reduce costs and complexity

# Application Configuration
#
# DNS for dev-api.infopaai.com now points at the dev instance's
# Elastic IP (18.222.113.112), so re-applying with this set will
# request its Let's Encrypt cert on boot. The EIP stays the same
# across this replacement (user_data_replace_on_change replaces the
# instance, not the EIP), so DNS doesn't need to be touched again.
domain        = "dev-api.infopaai.com"

# EC2 Configuration
instance_type = "t4g.small"
allowed_ports = ["22", "80", "443"]
