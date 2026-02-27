# Security Policy
## Reporting Vulnerabilities
If you discover a security vulnerability, please **do not** open a public issue. Instead, email the maintainer privately.
Please include:
- Description of the vulnerability
- Steps to reproduce (if applicable)
- Potential impact
- Suggested fix (if any)
We will respond within 48 hours.
## Security Best Practices
- Never commit `.env` files with sensitive data
- Use environment variables for secrets
- Keep dependencies updated
- Review pull requests carefully
- Run `pip-audit` to check for known vulnerabilities
## Deployment Security
When deploying to production:
- Use HTTPS/TLS for all communications
- Implement proper authentication and authorization
- Monitor logs for suspicious activity
- Keep systems patched and updated
For safety-critical deployments, additional security measures and compliance checks are required.
