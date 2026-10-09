# Contributing to Cert Sphere

Part of the **Media Sphere Open Source Community**.

Thank you for considering a contribution to Cert Sphere! We welcome code, documentation, testing, design, security, and usability contributions.

**Contact:** [mdatheeq.2004@gmail.com](mailto:mdatheeq.2004@gmail.com) or [mediasphere680@gmail.com](mailto:mediasphere680@gmail.com)

## Project vision

Cert Sphere is a bulk certificate generation and verification project. Its roadmap includes multiple certificate templates, issuer signatures, QR-based verification, secure certificate identifiers, email delivery, a public verification website, database improvements, containerization, and carefully scoped AI-assisted workflows.

Roadmap items are proposals unless they are already implemented and documented in the repository. Check existing issues and pull requests before starting substantial work.

## Ways to contribute

- Report reproducible bugs and suggest improvements.
- Add or improve tests and documentation.
- Improve PDF generation, validation, and job-status handling.
- Contribute to templates, QR verification, email delivery, database support, Docker, or AI integrations.
- Review pull requests and improve accessibility, security, and developer experience.

## Before you start

1. Search existing issues and pull requests.
2. For a significant change, open an issue or discussion first to agree on the approach.
3. For security vulnerabilities, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Development setup

The current backend uses Python, FastAPI, SQLAlchemy, ReportLab, and SQLite by default. Confirm the repository README and dependency files for the current supported setup.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

The API documentation is normally available at `http://127.0.0.1:8000/docs`.

Run tests before making changes and again before opening a pull request:

```bash
pytest
```

Use a development database and temporary storage. Never use real recipient data or production credentials in tests.

## Branches and commits

Create a focused branch from the default branch. Suggested prefixes:

- `feat/` — feature
- `fix/` — bug fix
- `docs/` — documentation
- `test/` — tests
- `refactor/` — refactoring
- `security/` — security improvement

Example:

```bash
git checkout -b feat/qr-verification
git add .
git commit -m "feat: add QR certificate verification"
```

Keep commits focused and write descriptive commit messages.

## Code guidelines

- Follow the existing project structure and conventions.
- Keep API routes, schemas, database access, PDF rendering, and background processing appropriately separated.
- Validate external input and handle individual-recipient failures without unnecessarily stopping a bulk job.
- Avoid adding dependencies unless there is a clear benefit.
- Update documentation and tests when behavior or configuration changes.
- Never commit credentials, private keys, personal recipient data, generated production certificates, or local database files.
- For verification features, do not treat a plain hash or an obscured identifier as a substitute for a secure verification design. Use cryptographically secure tokens and appropriate signature verification where required.
- AI-assisted contributions are welcome, but contributors are responsible for reviewing, testing, understanding, and being able to explain the code they submit.

## Tests

Add or update tests for changed behavior. Depending on the change, cover:

- Valid and invalid input.
- Job creation, status, and progress.
- Certificate generation and individual generation failures.
- Download and archive behavior.
- QR and verification outcomes, including revoked or unknown certificates where supported.
- Database consistency and relevant security boundaries.

Include the commands run and their results in your pull request. Do not claim tests passed unless you ran them successfully.

## Pull requests

1. Push your branch to your fork.
2. Open a pull request against the repository's default branch.
3. Explain the problem, solution, and scope.
4. Link related issues.
5. List tests run and results.
6. Document any migration, configuration, or compatibility changes.
7. Include screenshots or sample output when useful.

Use the pull request template in `.github/pull_request_template.md`. Keep pull requests focused and reasonably sized. Maintainers may request changes or decline work that is out of scope, unsafe, duplicated, or insufficiently tested.

## Security and privacy

Do not publish vulnerability details in a public issue. Follow [SECURITY.md](SECURITY.md) for private reporting. Avoid exposing recipient personal information on public verification pages; return only the information needed to establish certificate validity.

## Community

All participants are expected to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Be respectful, constructive, and open to feedback.

Thank you for helping build Cert Sphere as part of the Media Sphere Open Source Community.
