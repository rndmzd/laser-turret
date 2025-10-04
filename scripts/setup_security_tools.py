#!/usr/bin/env python3
"""
Setup script for security scanning tools
Installs and configures all required security tools
"""
import subprocess
import sys
import os


def run_command(cmd, description):
    """Run a command and print status"""
    print(f"\n{'='*60}")
    print(f"📦 {description}")
    print(f"{'='*60}")
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"✅ {description} - SUCCESS")
        if result.stdout:
            print(result.stdout)
    else:
        print(f"❌ {description} - FAILED")
        if result.stderr:
            print(result.stderr)
        return False
    
    return True


def main():
    """Main setup function"""
    print("""
    🔒 Security Tools Setup
    ========================
    
    This script will install and configure:
    - Safety (dependency vulnerability scanner)
    - Bandit (Python code security analyzer)
    - pip-audit (CVE database scanner)
    - Semgrep (advanced code scanner)
    - detect-secrets (secret detection)
    - pip-licenses (license compliance)
    """)
    
    response = input("\nProceed with installation? (y/N): ")
    if response.lower() != 'y':
        print("Installation cancelled.")
        return 1
    
    # Install tools
    tools = [
        ("pip3 install --upgrade pip", "Upgrading pip"),
        ("pip3 install safety bandit pip-audit semgrep detect-secrets pip-licenses", "Installing security tools"),
    ]
    
    for cmd, desc in tools:
        if not run_command(cmd, desc):
            print(f"\n⚠️  Warning: {desc} failed, but continuing...")
    
    # Create .security directory
    os.makedirs(".security", exist_ok=True)
    print("\n✅ Created .security directory")
    
    # Create Bandit config
    bandit_config = """[bandit]
exclude_dirs = ["/tests", "/venv", "/.venv", "/env"]
skips = []
tests = []

[bandit.formatters]
html = {enabled: true, output: ".security/bandit-report.html"}
json = {enabled: true, output: ".security/bandit-report.json"}
txt = {enabled: true, output: ".security/bandit-report.txt"}
"""
    
    with open(".bandit", "w") as f:
        f.write(bandit_config)
    print("✅ Created .bandit configuration")
    
    # Create Semgrep config
    semgrep_config = """rules:
  - id: hardcoded-password
    pattern: password = "..."
    message: Possible hardcoded password detected
    severity: ERROR
    languages: [python]
    
  - id: sql-injection
    pattern: execute($SQL)
    message: Possible SQL injection vulnerability
    severity: ERROR
    languages: [python]
    
  - id: command-injection
    patterns:
      - pattern: os.system($CMD)
      - pattern-not: os.system("...")
    message: Possible command injection vulnerability
    severity: ERROR
    languages: [python]
    
  - id: insecure-random
    pattern: random.random()
    message: Use secrets module for cryptographic randomness
    severity: WARNING
    languages: [python]
    
  - id: eval-usage
    pattern: eval(...)
    message: Avoid using eval() - security risk
    severity: ERROR
    languages: [python]
    
  - id: pickle-usage
    pattern: pickle.loads(...)
    message: Pickle deserialization can execute arbitrary code
    severity: WARNING
    languages: [python]
"""
    
    with open(".semgrep.yml", "w") as f:
        f.write(semgrep_config)
    print("✅ Created .semgrep.yml configuration")
    
    # Initialize detect-secrets
    run_command("detect-secrets scan --baseline .secrets.baseline", "Initializing detect-secrets baseline")
    
    # Test installations
    print(f"\n{'='*60}")
    print("🧪 Testing Installations")
    print(f"{'='*60}\n")
    
    test_commands = [
        ("safety --version", "Safety"),
        ("bandit --version", "Bandit"),
        ("pip-audit --version", "pip-audit"),
        ("semgrep --version", "Semgrep"),
        ("detect-secrets --version", "detect-secrets"),
        ("pip-licenses --version", "pip-licenses"),
    ]
    
    all_ok = True
    for cmd, tool in test_commands:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            version = result.stdout.strip() or result.stderr.strip()
            print(f"✅ {tool:20} - {version.split()[0] if version else 'OK'}")
        else:
            print(f"❌ {tool:20} - NOT INSTALLED")
            all_ok = False
    
    print(f"\n{'='*60}")
    if all_ok:
        print("✅ All security tools installed successfully!")
        print(f"{'='*60}\n")
        print("Next steps:")
        print("1. Run a security scan: safety check && pip-audit && bandit -r .")
        print("2. Use the /security-scan workflow in Windsurf")
        print("3. View reports in .security/ directory")
        print("4. Set up CI/CD integration (see .github/workflows/security.yml)")
    else:
        print("⚠️  Some tools failed to install. Check errors above.")
        print(f"{'='*60}\n")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
