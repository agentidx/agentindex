#!/usr/bin/env python3
"""
Continuous Security Monitor for AgentIndex Infrastructure
Implements ongoing security assessment and best practice recommendations
"""

import subprocess
import json
from datetime import datetime
import os

class ContinuousSecurityMonitor:
    def __init__(self):
        self.security_checks = []
        self.recommendations = []
        self.critical_issues = []
        
    def check_web_security_headers(self):
        """Check security headers on web endpoints"""
        endpoints = [
            'https://agentcrawl.dev',
            'https://api.agentcrawl.dev',
            'https://dash.agentcrawl.dev'
        ]
        
        security_headers = [
            'Content-Security-Policy',
            'X-Frame-Options', 
            'X-Content-Type-Options',
            'Strict-Transport-Security',
            'X-XSS-Protection'
        ]
        
        results = {}
        for endpoint in endpoints:
            try:
                result = subprocess.run(['curl', '-s', '-I', endpoint], 
                                     capture_output=True, text=True, timeout=10)
                headers = result.stdout.lower()
                
                endpoint_security = {}
                for header in security_headers:
                    endpoint_security[header] = header.lower() in headers
                
                results[endpoint] = endpoint_security
                
                # Check for security issues
                missing_headers = [h for h, present in endpoint_security.items() if not present]
                if missing_headers:
                    self.recommendations.append({
                        'priority': 'high',
                        'endpoint': endpoint,
                        'issue': f'Missing security headers: {missing_headers}',
                        'fix': f'Add headers to web server configuration'
                    })
                    
            except Exception as e:
                self.critical_issues.append({
                    'endpoint': endpoint,
                    'error': f'Failed to check headers: {e}'
                })
        
        return results
    
    def check_exposed_endpoints(self):
        """Check for exposed debug/admin endpoints"""
        sensitive_paths = [
            '/admin', '/debug', '/.env', '/config', 
            '/status', '/.git', '/backup', '/logs'
        ]
        
        base_urls = ['https://agentcrawl.dev', 'https://api.agentcrawl.dev']
        exposed = []
        
        for base_url in base_urls:
            for path in sensitive_paths:
                try:
                    result = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', 
                                           f'{base_url}{path}'], capture_output=True, text=True, timeout=5)
                    status_code = result.stdout.strip()
                    
                    if status_code in ['200', '301', '302']:
                        exposed.append(f'{base_url}{path} (HTTP {status_code})')
                        self.critical_issues.append({
                            'severity': 'critical',
                            'endpoint': f'{base_url}{path}',
                            'issue': f'Exposed sensitive path returning HTTP {status_code}',
                            'fix': 'Block access to sensitive paths in web server configuration'
                        })
                        
                except Exception:
                    pass  # Timeout or connection error is expected for many paths
        
        return exposed
    
    def check_api_security(self):
        """Check API security configuration"""
        api_checks = {}
        
        try:
            # Check if API requires authentication for sensitive endpoints
            result = subprocess.run(['curl', '-s', 'https://api.agentcrawl.dev/v1/'], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                response = result.stdout
                api_checks['accessible'] = True
                
                # Check for rate limiting headers
                headers_result = subprocess.run(['curl', '-s', '-I', 'https://api.agentcrawl.dev/v1/health'], 
                                              capture_output=True, text=True, timeout=10)
                headers = headers_result.stdout.lower()
                
                api_checks['rate_limiting'] = 'x-ratelimit' in headers or 'rate-limit' in headers
                
                if not api_checks['rate_limiting']:
                    self.recommendations.append({
                        'priority': 'medium',
                        'component': 'API',
                        'issue': 'No rate limiting headers detected',
                        'fix': 'Implement rate limiting to prevent abuse'
                    })
                    
        except Exception as e:
            api_checks['error'] = str(e)
        
        return api_checks
    
    def check_database_security(self):
        """Check database security configuration"""
        db_checks = {}
        
        # Check if database files have proper permissions
        db_files = ['agentindex.db', 'cost_tracking.db', 'system_monitor.db']
        
        for db_file in db_files:
            if os.path.exists(db_file):
                stat_info = os.stat(db_file)
                permissions = oct(stat_info.st_mode)[-3:]
                
                # Database should not be world-readable (no 4 in last digit)
                if permissions[-1] in ['4', '5', '6', '7']:
                    self.recommendations.append({
                        'priority': 'high',
                        'file': db_file,
                        'issue': f'Database file has world-readable permissions: {permissions}',
                        'fix': f'chmod 600 {db_file}'
                    })
                
                db_checks[db_file] = {
                    'permissions': permissions,
                    'secure': permissions[-1] not in ['4', '5', '6', '7']
                }
        
        return db_checks
    
    def check_secrets_exposure(self):
        """Check for exposed secrets or credentials"""
        secret_patterns = ['.env', 'config.json', 'credentials', 'secrets', 'keys']
        exposed_secrets = []
        
        # Check for secret files in web-accessible locations
        for pattern in secret_patterns:
            try:
                result = subprocess.run(['find', 'static/', '-name', f'*{pattern}*'], 
                                      capture_output=True, text=True)
                if result.stdout.strip():
                    exposed_secrets.extend(result.stdout.strip().split('\\n'))
                    
            except Exception:
                pass
        
        if exposed_secrets:
            self.critical_issues.append({
                'severity': 'critical',
                'issue': f'Potential secret files in web-accessible directory: {exposed_secrets}',
                'fix': 'Move secret files outside web root, add to .gitignore'
            })
        
        return exposed_secrets
    
    def generate_security_report(self):
        """Generate comprehensive security assessment report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'assessment_results': {},
            'security_score': 0,
            'recommendations': self.recommendations,
            'critical_issues': self.critical_issues
        }
        
        # Run all security checks
        print('🔒 RUNNING CONTINUOUS SECURITY ASSESSMENT')
        print('=' * 50)
        
        print('1. Checking web security headers...')
        report['assessment_results']['web_headers'] = self.check_web_security_headers()
        
        print('2. Scanning for exposed endpoints...')
        report['assessment_results']['exposed_endpoints'] = self.check_exposed_endpoints()
        
        print('3. Analyzing API security...')
        report['assessment_results']['api_security'] = self.check_api_security()
        
        print('4. Checking database permissions...')
        report['assessment_results']['database_security'] = self.check_database_security()
        
        print('5. Scanning for exposed secrets...')
        report['assessment_results']['secrets_exposure'] = self.check_secrets_exposure()
        
        # Calculate security score
        total_checks = 0
        passed_checks = 0
        
        # Score web headers
        for endpoint, headers in report['assessment_results']['web_headers'].items():
            for header, present in headers.items():
                total_checks += 1
                if present:
                    passed_checks += 1
        
        # Score other checks
        if not report['assessment_results']['exposed_endpoints']:
            passed_checks += 5  # No exposed endpoints is good
        total_checks += 5
        
        if report['assessment_results']['api_security'].get('rate_limiting', False):
            passed_checks += 1
        total_checks += 1
        
        # Database security
        for db, info in report['assessment_results']['database_security'].items():
            total_checks += 1
            if info['secure']:
                passed_checks += 1
        
        if not report['assessment_results']['secrets_exposure']:
            passed_checks += 1
        total_checks += 1
        
        report['security_score'] = int((passed_checks / total_checks) * 100) if total_checks > 0 else 0
        
        return report
    
    def print_security_summary(self, report):
        """Print security assessment summary"""
        print('\\n📊 SECURITY ASSESSMENT SUMMARY')
        print(f'Overall Security Score: {report["security_score"]}/100')
        
        if report['critical_issues']:
            print(f'\\n🚨 CRITICAL ISSUES ({len(report[\"critical_issues\"])}):')
            for issue in report['critical_issues']:
                print(f'• {issue[\"issue\"]}')
                print(f'  Fix: {issue[\"fix\"]}')
        
        if report['recommendations']:
            print(f'\\n💡 RECOMMENDATIONS ({len(report[\"recommendations\"])}):')
            high_priority = [r for r in report['recommendations'] if r['priority'] == 'high']
            medium_priority = [r for r in report['recommendations'] if r['priority'] == 'medium']
            
            for rec in high_priority[:3]:  # Top 3 high priority
                print(f'🔴 HIGH: {rec[\"issue\"]}')
                print(f'   Fix: {rec[\"fix\"]}')
            
            for rec in medium_priority[:2]:  # Top 2 medium priority  
                print(f'🟡 MEDIUM: {rec[\"issue\"]}')
                print(f'   Fix: {rec[\"fix\"]}')
        
        if report['security_score'] >= 90:
            print('✅ Security posture: EXCELLENT')
        elif report['security_score'] >= 75:
            print('⚠️ Security posture: GOOD (improvements recommended)')
        else:
            print('🚨 Security posture: NEEDS IMPROVEMENT (action required)')

def main():
    monitor = ContinuousSecurityMonitor()
    report = monitor.generate_security_report()
    monitor.print_security_summary(report)
    
    # Save report
    with open('security_assessment_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f'\\n💾 Security report saved: security_assessment_report.json')
    print('🔄 Run this regularly for continuous security monitoring')

if __name__ == '__main__':
    main()