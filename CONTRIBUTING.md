# Contributing

This is a personal HomeLab automation project shared for reference. While not actively seeking contributions, bug reports and suggestions are welcome.

## Reporting Issues

- **Bug Reports**: Open GitHub Issues with reproduction steps
- **Questions**: Use GitHub Discussions for setup questions
- **Documentation**: Report unclear instructions or missing details

## Making Changes

If you want to adapt this for your own environment:

1. **Fork the repository**
2. **Modify for your needs** - change IPs, domains, hardware specs
3. **Test thoroughly** - validate in your own lab first
4. **Share improvements** - PRs welcome for general fixes or enhancements

## Basic Standards

- **Test first**: Run `./ansible/test_ansible_syntax.sh`
- **Keep secrets out**: Use environment variables, never commit credentials
- **Document changes**: Update relevant README or role docs
- **Simple commits**: Clear commit messages describing what changed

## What This Project Covers

- SSL certificate automation with internal CA
- HashiCorp Vault deployment and management  
- Prometheus monitoring stack
- Jenkins and GitLab Runner integration
- Automated system patching
- Docker container management

This is designed for Raspberry Pi + Fedora server environments but can be adapted for other setups.

## Support

This is a reference implementation - no formal support provided. Check existing documentation and issues first, then open a GitHub Issue if needed.