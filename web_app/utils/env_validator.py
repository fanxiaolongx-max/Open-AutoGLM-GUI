# -*- coding: utf-8 -*-
"""
Environment validation utility.

Validates the Python environment before application startup to prevent
common errors like missing virtual environment activation or incompatible
dependency versions.
"""

import sys
import os
from pathlib import Path
from typing import List, Tuple, Optional
import importlib.metadata
from packaging import version
import re


class ValidationError(Exception):
    """Raised when environment validation fails."""
    pass


class EnvironmentValidator:
    """Validates the Python runtime environment."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.errors: List[str] = []
        self.warnings: List[str] = []
        
    def validate_all(self, strict: bool = False) -> bool:
        """
        Run all validation checks.
        
        Args:
            strict: If True, warnings are treated as errors
            
        Returns:
            True if validation passes, False otherwise
        """
        self.errors.clear()
        self.warnings.clear()
        
        # Run all checks
        self._check_python_version()
        self._check_virtual_environment()
        self._check_critical_dependencies()
        
        # Determine success
        has_errors = len(self.errors) > 0
        has_warnings = len(self.warnings) > 0
        
        if has_errors:
            return False
        elif strict and has_warnings:
            return False
        
        return True
    
    def _check_python_version(self):
        """Check if Python version meets minimum requirements."""
        min_version = (3, 8)
        current = sys.version_info[:2]
        
        if current < min_version:
            self.errors.append(
                f"Python {min_version[0]}.{min_version[1]}+ required, "
                f"but found {current[0]}.{current[1]}"
            )
    
    def _check_virtual_environment(self):
        """Check if running inside a virtual environment."""
        # Check common virtual environment indicators
        in_venv = (
            hasattr(sys, 'real_prefix') or  # virtualenv
            (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix) or  # venv
            os.environ.get('VIRTUAL_ENV') is not None  # environment variable
        )
        
        if not in_venv:
            venv_path = self.project_root / "venv"
            activate_script = venv_path / "bin" / "activate"
            
            warning_msg = (
                "⚠️  Virtual environment not activated!\n"
                "   This may cause dependency conflicts and errors.\n"
            )
            
            if venv_path.exists() and activate_script.exists():
                warning_msg += (
                    f"\n   To activate the virtual environment, run:\n"
                    f"   source {activate_script}\n"
                )
            else:
                warning_msg += (
                    f"\n   To create and activate a virtual environment:\n"
                    f"   python3 -m venv venv\n"
                    f"   source venv/bin/activate\n"
                    f"   pip install -r requirements.txt\n"
                )
            
            self.warnings.append(warning_msg)
    
    def _check_critical_dependencies(self):
        """Check if critical dependencies are installed with correct versions."""
        requirements_file = self.project_root / "requirements.txt"
        
        if not requirements_file.exists():
            self.warnings.append(
                f"requirements.txt not found at {requirements_file}"
            )
            return
        
        # Parse requirements.txt
        critical_packages = self._parse_requirements(requirements_file)
        
        # Check each critical package
        for package_name, version_spec in critical_packages:
            self._check_package(package_name, version_spec)
    
    def _parse_requirements(self, requirements_file: Path) -> List[Tuple[str, Optional[str]]]:
        """
        Parse requirements.txt file.
        
        Returns:
            List of (package_name, version_spec) tuples
        """
        packages = []
        
        with open(requirements_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Skip commented out packages
                if line.startswith('# '):
                    continue
                
                # Parse package name and version
                # Handle formats like: package>=1.0.0, package[extra]>=1.0.0, package==1.0.0, package
                # First, extract package name (before version specifier)
                match = re.match(r'^([a-zA-Z0-9\-_]+)(\[[^\]]+\])?(>=|==|<=|>|<|~=)?(.+)?$', line)
                if match:
                    package = match.group(1).lower().replace('_', '-')
                    # group(2) is the extras part like [standard], we ignore it for checking
                    operator = match.group(3) if match.group(3) else None
                    ver = match.group(4) if match.group(4) else None
                    
                    if operator and ver:
                        packages.append((package, f"{operator}{ver}"))
                    else:
                        packages.append((package, None))
        
        return packages

    
    def _check_package(self, package_name: str, version_spec: Optional[str]):
        """
        Check if a package is installed and meets version requirements.
        
        Args:
            package_name: Package name (e.g., 'fastapi')
            version_spec: Version specification (e.g., '>=0.100.0')
        """
        # Normalize package name (replace - with _)
        normalized_name = package_name.replace('-', '_')
        
        try:
            # Try to get installed version
            try:
                installed_version = importlib.metadata.version(package_name)
            except importlib.metadata.PackageNotFoundError:
                # Try with normalized name
                installed_version = importlib.metadata.version(normalized_name)
            
            # If version spec is provided, check compatibility
            if version_spec:
                self._check_version_compatibility(
                    package_name, installed_version, version_spec
                )
                
        except importlib.metadata.PackageNotFoundError:
            # Special handling for python-telegram-bot
            if 'telegram' in package_name.lower():
                self.errors.append(
                    f"❌ Critical package '{package_name}' is not installed!\n"
                    f"   This is likely because the virtual environment is not activated.\n"
                    f"   The error you saw ('Updater' object has no attribute...) \n"
                    f"   is caused by using the wrong version of python-telegram-bot.\n"
                    f"\n"
                    f"   Please activate the virtual environment and try again:\n"
                    f"   source venv/bin/activate\n"
                )
            else:
                self.errors.append(
                    f"❌ Required package '{package_name}' is not installed"
                )
    
    def _check_version_compatibility(
        self, package_name: str, installed: str, spec: str
    ):
        """
        Check if installed version meets the version specification.
        
        Args:
            package_name: Package name
            installed: Installed version string
            spec: Version specification (e.g., '>=1.0.0')
        """
        # Parse operator and version from spec
        match = re.match(r'^(>=|==|<=|>|<|~=)(.+)$', spec)
        if not match:
            return
        
        operator = match.group(1)
        required = match.group(2).strip()
        
        try:
            installed_ver = version.parse(installed)
            required_ver = version.parse(required)
            
            compatible = False
            if operator == '>=':
                compatible = installed_ver >= required_ver
            elif operator == '==':
                compatible = installed_ver == required_ver
            elif operator == '<=':
                compatible = installed_ver <= required_ver
            elif operator == '>':
                compatible = installed_ver > required_ver
            elif operator == '<':
                compatible = installed_ver < required_ver
            elif operator == '~=':
                # Compatible release (same major.minor)
                compatible = (
                    installed_ver.major == required_ver.major and
                    installed_ver.minor == required_ver.minor and
                    installed_ver >= required_ver
                )
            
            if not compatible:
                self.errors.append(
                    f"❌ Package '{package_name}' version mismatch:\n"
                    f"   Required: {spec}\n"
                    f"   Installed: {installed}\n"
                    f"   Please reinstall dependencies: pip install -r requirements.txt"
                )
                
        except Exception as e:
            self.warnings.append(
                f"Could not verify version for {package_name}: {e}"
            )
    
    def print_results(self):
        """Print validation results to console."""
        if self.errors:
            print("\n" + "=" * 70)
            print("❌ ENVIRONMENT VALIDATION FAILED")
            print("=" * 70)
            
            for error in self.errors:
                print(f"\n{error}")
            
            print("\n" + "=" * 70)
            print("Please fix the errors above before starting the application.")
            print("=" * 70 + "\n")
        
        if self.warnings:
            print("\n" + "=" * 70)
            print("⚠️  ENVIRONMENT WARNINGS")
            print("=" * 70)
            
            for warning in self.warnings:
                print(f"\n{warning}")
            
            print("=" * 70)
            print("The application will start, but you may encounter issues.")
            print("=" * 70 + "\n")


def validate_environment(project_root: Optional[Path] = None, strict: bool = False) -> bool:
    """
    Validate the Python environment.
    
    Args:
        project_root: Path to project root (defaults to parent of this file)
        strict: If True, warnings are treated as errors
        
    Returns:
        True if validation passes, False otherwise
    """
    if project_root is None:
        # Default to project root (3 levels up from this file)
        project_root = Path(__file__).resolve().parent.parent.parent
    
    validator = EnvironmentValidator(project_root)
    is_valid = validator.validate_all(strict=strict)
    validator.print_results()
    
    return is_valid
