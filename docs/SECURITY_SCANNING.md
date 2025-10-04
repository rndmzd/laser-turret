# Security Vulnerability Scanning

This document provides an overview of the security scanning infrastructure for the laser-turret project.

## 🎯 Quick Start

### Option 1: Use the Workflow (Recommended)

```bash
# In Windsurf, use the slash command:
/security-scan
```

### Option 2: Manual Setup

```bash
# Run the setup script
python3 scripts/setup_security_tools.py

# Run a comprehensive scan
safety check && pip-audit && bandit -r . && semgrep --config=p/security-audit .
```

## 📋 What's Included

### Security Tools

1. **Safety** - Checks Python dependencies against known vulnerability database
2. **pip-audit** - Scans dependencies using CVE database
3. **Bandit** - Static analysis for Python code security issues
4. **Semgrep** - Advanced code scanning with custom rules
5. **detect-secrets** - Prevents committing secrets to repository
6. **pip-licenses** - License compliance checking

### Files Created

```
.windsurf/workflows/
  └── security-scan.md          # Complete workflow guide

.security/
  └── README.md                  # Security reports documentation
  
scripts/
  ├── setup_security_tools.py    # Automated setup script
  ├── auto_update_vulnerable_deps.py  # Auto-remediation script
  └── generate_security_dashboard.py  # HTML dashboard generator

.github/workflows/
  └── security.yml               # CI/CD integration (to be created)

Configuration files:
  ├── .bandit                    # Bandit configuration
  ├── .semgrep.yml              # Semgrep rules
  └── .secrets.baseline         # Secret detection baseline
```

## 🔍 Scan Types

### On-Demand Scans

Run individual scans as needed:

```bash
# Dependency vulnerabilities
safety check
pip-audit --desc

# Code security issues
bandit -r .
semgrep --config=p/security-audit .

# Secret detection
detect-secrets scan --baseline .secrets.baseline --all-files

# License compliance
pip-licenses --summary
```

### Comprehensive Scan

Run all scans at once:

```bash
# Use the workflow for guided execution
/security-scan

# Or run manually
safety check && pip-audit && bandit -r . && semgrep --config=p/security-audit . && detect-secrets scan
```

## 🤖 CI/CD Integration

### GitHub Actions

The workflow includes a complete GitHub Actions configuration that:

- ✅ Runs on every push to main/develop
- ✅ Runs on all pull requests
- ✅ Scheduled weekly scans (Mondays 9 AM UTC)
- ✅ Allows manual workflow dispatch
- ✅ Uploads reports as artifacts
- ✅ Integrates with GitHub Security tab

To enable:

1. The workflow file template is in `.windsurf/workflows/security-scan.md`
2. Copy the GitHub Actions section to `.github/workflows/security.yml`
3. Commit and push to enable automated scanning

### Pre-commit Hooks

Add security checks to run before every commit:

```bash
# Install pre-commit
pip install pre-commit

# Add security hooks (template in workflow)
# Then install hooks
pre-commit install
```

## 📊 Reports & Dashboard

### View Reports

All scan reports are saved to `.security/` directory:

```bash
# View Bandit findings
cat .security/bandit-report.json | jq '.results'

# View Safety vulnerabilities
cat .security/safety-report.json | jq

# Generate HTML dashboard
python3 scripts/generate_security_dashboard.py
```

### Dashboard

The HTML dashboard provides a consolidated view:

```bash
# Generate dashboard
python3 scripts/generate_security_dashboard.py

# Open in browser
start .security/dashboard.html  # Windows
open .security/dashboard.html   # macOS
xdg-open .security/dashboard.html  # Linux
```

## 🔧 Auto-Remediation

### Update Vulnerable Dependencies

Automatically update packages with known vulnerabilities:

```bash
python3 scripts/auto_update_vulnerable_deps.py
```

This script:

1. Scans for vulnerable dependencies
2. Shows which packages need updating
3. Prompts for confirmation
4. Updates packages automatically
5. Re-scans to verify fixes

## 🚨 Severity Levels

- **CRITICAL/HIGH** - Immediate action required, potential security breach
- **MEDIUM** - Should be addressed soon, moderate risk
- **LOW** - Minor issues, address when convenient
- **INFO** - Informational findings, no immediate risk

## 📝 Best Practices

1. **Run scans regularly** - Weekly at minimum, before every release
2. **Review all findings** - Some may be false positives
3. **Prioritize by severity** - Address CRITICAL/HIGH first
4. **Keep tools updated** - Security databases are constantly updated
5. **Integrate into CI/CD** - Automate scanning in your pipeline
6. **Document exclusions** - Track false positives and why they're excluded
7. **Rotate secrets immediately** - If secrets are detected, rotate them
8. **Monitor dependencies** - Enable Dependabot or similar tools

## 🔐 Secret Management

### Prevent Secret Commits

```bash
# Initialize baseline
detect-secrets scan --baseline .secrets.baseline

# Scan for new secrets
detect-secrets scan --baseline .secrets.baseline --all-files

# Audit findings
detect-secrets audit .secrets.baseline
```

### If Secrets Are Found

1. **Immediately rotate** the compromised credentials
2. **Remove from git history** using tools like `git-filter-repo`
3. **Update baseline** to prevent future commits
4. **Review access logs** for unauthorized usage

## 🛠️ Troubleshooting

### Installation Issues

```bash
# Upgrade pip first
pip3 install --upgrade pip

# Install tools one by one if batch fails
pip3 install safety
pip3 install bandit
pip3 install pip-audit
pip3 install semgrep
pip3 install detect-secrets
```

### False Positives

Add exclusions to configuration files:

- **Bandit**: Edit `.bandit` to skip specific tests or directories
- **Semgrep**: Modify `.semgrep.yml` to adjust rules
- **detect-secrets**: Use `detect-secrets audit` to mark false positives

### CI/CD Failures

- Check tool versions in GitHub Actions
- Review scan thresholds (may need adjustment)
- Ensure all configuration files are committed
- Verify network access for vulnerability databases

## 📚 Additional Resources

- [Safety Documentation](https://pyup.io/safety/)
- [Bandit Documentation](https://bandit.readthedocs.io/)
- [pip-audit Documentation](https://pypi.org/project/pip-audit/)
- [Semgrep Documentation](https://semgrep.dev/docs/)
- [detect-secrets Documentation](https://github.com/Yelp/detect-secrets)

## 🔄 Workflow Commands

All available security scanning commands:

```bash
# Setup
/security-scan                    # Full workflow guide
python3 scripts/setup_security_tools.py  # Automated setup

# Scanning
safety check                      # Dependency scan (Safety)
pip-audit --desc                  # Dependency scan (CVE)
bandit -r .                       # Code security scan
semgrep --config=p/security-audit .  # Advanced code scan
detect-secrets scan               # Secret detection

# Remediation
python3 scripts/auto_update_vulnerable_deps.py  # Auto-update

# Reporting
python3 scripts/generate_security_dashboard.py  # Generate dashboard
```

## 📞 Support

For issues or questions:

1. Check the workflow documentation: `.windsurf/workflows/security-scan.md`
2. Review tool-specific documentation (links above)
3. Check `.security/README.md` for report information
4. Review GitHub Actions logs for CI/CD issues

---

**Last Updated**: October 2025  
**Maintained By**: Laser Turret Security Team
