# Contributing to AgentIndex

Thank you for your interest in contributing to AgentIndex! We're building the semantic discovery layer for AI agents, and community contributions are essential.

## 🎯 Ways to Contribute

### 🔍 Report Missing Agents
Found an AI agent that should be indexed but isn't? Help us expand coverage:

**What we're looking for:**
- Production-ready AI agents
- Well-documented tools with clear setup
- Active maintenance (commits within 6 months)
- Framework integration (LangChain, CrewAI, AutoGen, etc.)

**How to submit:**
1. [Create an issue](https://github.com/agentidx/agentindex/issues/new) with template "Missing Agent"
2. Provide: Agent URL, description, framework, capabilities
3. We'll review and index within 48 hours

### 📊 Improve Trust Scoring
Our 6-component trust algorithm can always be better:

**Current factors:**
- Maintenance activity (25%)
- Community adoption (20%)  
- Documentation quality (15%)
- Code stability (15%)
- Security practices (15%)
- Performance characteristics (10%)

**Contribute improvements:**
- Algorithm refinements
- New quality indicators
- Benchmark datasets
- Performance optimizations

### 🔧 Framework Integrations
Help us support more AI frameworks:

**Priority frameworks:**
- Microsoft Semantic Kernel
- Haystack
- Rasa
- spaCy ecosystem
- Custom enterprise frameworks

**Integration requirements:**
- SDK package (Python/Node.js)
- Documentation with examples
- Test coverage
- Performance benchmarks

### 📝 Documentation & Examples
Developer-focused content that helps adoption:

- Integration tutorials
- Production deployment guides  
- Performance optimization tips
- Real-world use case examples
- Video demonstrations

## 🛠️ Development Setup

### Prerequisites
- Python 3.9+
- Node.js 18+
- PostgreSQL 14+
- Redis 6+

### Local Setup
```bash
# Clone repository
git clone https://github.com/agentidx/agentindex.git
cd agentindex

# Python environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Database setup
createdb agentindex
python -m agentindex.db.migrate

# Environment configuration  
cp .env.example .env
# Edit .env with your configuration

# Start services
python -m agentindex.run
```

### Development Commands
```bash
# Run tests
pytest tests/

# Type checking
mypy agentindex/

# Code formatting
black agentindex/
isort agentindex/

# API documentation
python -m agentindex.docs

# Build semantic index
python -m agentindex.api.semantic
```

## 🧪 Testing

### Running Tests
```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# Integration tests  
pytest tests/integration/

# API tests
pytest tests/api/

# Performance tests
pytest tests/performance/ --benchmark-only
```

### Test Coverage
Maintain >90% coverage:
```bash
pytest --cov=agentindex --cov-report=html
open htmlcov/index.html
```

### Test Data
Use provided fixtures for consistent testing:
```python
# tests/fixtures/agents.py
from agentindex.testing import create_test_agent

def test_search_functionality():
    agent = create_test_agent(
        name="Test Agent",
        trust_score=85,
        framework="langchain"
    )
    results = search("test query")
    assert len(results) > 0
```

## 📋 Pull Request Process

### Before Submitting
1. **Create an issue** discussing the change (unless trivial)
2. **Fork the repository** and create a feature branch
3. **Write tests** for new functionality
4. **Update documentation** if needed
5. **Run full test suite** and ensure it passes

### PR Requirements
```bash
# Checklist before submitting:
□ Tests pass locally
□ Code follows style guidelines (black, isort)
□ Documentation updated
□ Performance impact considered
□ Breaking changes documented
□ CHANGELOG.md updated
```

### PR Template
```markdown
## Description
Brief description of the change and motivation.

## Type of Change
- [ ] Bug fix (non-breaking change)
- [ ] New feature (non-breaking change)  
- [ ] Breaking change (affects existing functionality)
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing performed

## Performance Impact
Describe any performance implications.

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Tests added for new functionality
```

## 🎨 Code Style

### Python
Follow PEP 8 with these specifics:
```python
# Use black formatting
black agentindex/

# Import organization with isort
isort agentindex/

# Type hints required for public APIs
def search(query: str, limit: int = 10) -> List[Agent]:
    pass

# Docstrings for all public functions
def search(query: str) -> List[Agent]:
    """
    Semantic search across indexed agents.
    
    Args:
        query: Natural language search query
        
    Returns:
        List of matching agents with trust scores
    """
```

### JavaScript/TypeScript
```typescript
// Use Prettier formatting
// TypeScript required for SDKs
export interface SearchResult {
  agent_id: string
  name: string
  trust_score: number
}

export async function search(query: string): Promise<SearchResult[]> {
  // Implementation
}
```

## 🔒 Security Guidelines

### API Security
- Always validate input parameters
- Use parameterized queries (no SQL injection)
- Rate limiting on all endpoints
- API key validation for protected routes

### Data Handling
- No sensitive data in logs
- Encrypt API keys and credentials
- Sanitize user inputs
- Follow GDPR/privacy guidelines

### Reporting Security Issues
**DO NOT** create public issues for security vulnerabilities.

Email: security@agentindex.ai
- We'll respond within 24 hours
- Coordinated disclosure process
- Recognition in security acknowledgments

## 🏷️ Issue Labels

**Type:**
- `bug` - Something isn't working
- `feature` - New functionality request
- `improvement` - Enhancement to existing feature
- `documentation` - Docs related

**Priority:**
- `critical` - Breaks core functionality
- `high` - Important for next release
- `medium` - Nice to have
- `low` - Future consideration

**Status:**
- `help-wanted` - Good for contributors
- `good-first-issue` - Beginner friendly
- `blocked` - Cannot proceed yet
- `in-progress` - Being worked on

## 🚀 Release Process

### Version Numbering
We use Semantic Versioning (semver.org):
- `MAJOR.MINOR.PATCH`
- `MAJOR`: Breaking changes
- `MINOR`: New features (backwards compatible)
- `PATCH`: Bug fixes

### Release Checklist
1. Update CHANGELOG.md
2. Bump version in all relevant files
3. Create release branch
4. Full test suite passes
5. Performance regression tests
6. Documentation updates
7. Create GitHub release
8. Deploy to production
9. Announce in community channels

## 💬 Community Guidelines

### Code of Conduct
We follow the [Contributor Covenant](https://www.contributor-covenant.org/):
- Be respectful and inclusive
- Constructive feedback only
- Focus on technical merits
- Help newcomers learn

### Communication Channels
- **GitHub Issues**: Bug reports, feature requests
- **GitHub Discussions**: Design discussions, questions
- **Discord**: Real-time community support
- **Email**: Private security/business concerns

### Getting Help
1. **Search existing issues** - Your question may be answered
2. **Check documentation** - Comprehensive guides available
3. **Ask in Discord** - Community support
4. **Create GitHub issue** - For bugs or feature requests

## 🏆 Recognition

### Contributors
All contributors are recognized in:
- README.md contributors section
- Annual contributor spotlight
- Discord special roles
- Conference speaking opportunities (for major contributors)

### Contribution Types Valued
- Code contributions
- Documentation improvements
- Bug reports and testing
- Community support and mentoring
- Performance optimizations
- Security improvements

---

**Questions?** Join our [Discord](https://discord.gg/agentindex) or create an issue. We're here to help!

**Ready to contribute?** Check out [good first issues](https://github.com/agentidx/agentindex/labels/good%20first%20issue) to get started.