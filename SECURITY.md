# Security Policy

Cert Sphere takes the security of certificate generation, storage, delivery, and verification seriously.

## Reporting a vulnerability

**Please do not report security vulnerabilities in public issues or pull requests.**

Send a private report to either:

- [mediasphere680@gmail.com](mailto:mediasphere680@gmail.com)
- [mdatheeq.2004@gmail.com](mailto:mdatheeq.2004@gmail.com)

Use the subject line **Private Security Report — Cert Sphere**. Include, where possible:

- A description of the suspected vulnerability and its impact.
- Affected version, commit, endpoint, or component.
- Reproduction steps or a minimal proof of concept.
- Any suggested mitigation.

Do not include real recipients' personal data, live credentials, or private keys in the report. Redact sensitive information.

## What to expect

A maintainer will review the report and, where possible, acknowledge receipt and coordinate next steps with the reporter. Please allow reasonable time for investigation and a fix before public disclosure. No specific response-time guarantee is currently provided.

## Scope examples

Security-relevant areas may include:

- Unauthorized access to certificates, jobs, or stored files.
- Forged, tampered, or incorrectly verified certificates.
- Verification-token guessing or leakage.
- Unsafe file uploads, path traversal, or server-side request forgery.
- Exposure of personal data, secrets, or signing keys.
- Authentication, authorization, dependency, or deployment weaknesses.

## Responsible testing

Only test systems and data you own or have explicit permission to assess. Avoid destructive testing, service disruption, and access to other people's data. Stop testing and report the issue privately if sensitive information is exposed.

## Supported versions

Until a formal release-support policy is published, please report security issues affecting the latest version on the default branch. Maintainers will determine whether older releases are affected.
