# Privacy Policy

**Last updated:** February 2025

This privacy policy describes how **GemmaCrit** (this project and any associated services) may collect, use, and protect information when you use the software or any deployed instance.

## Scope

This policy applies to:

- This repository and its documentation
- Any deployment or instance of the GemmaCrit application you run or access
- Data you provide when using the application (e.g., uploaded protocol documents, user account information)

## Information We May Collect

Depending on how you use GemmaCrit:

- **Account and authentication data**: If you use login or OAuth (e.g., Google), we may receive identifiers such as email and name from the identity provider, as configured by the operator of the instance.
- **Usage data**: Logs of API requests, errors, and pipeline runs may be retained for debugging and operations.
- **Content you provide**: Clinical trial protocol PDFs and related inputs you upload are processed by the pipeline. How long they are stored depends on the deployment configuration.

## How We Use Information

- To operate and improve the eligibility extraction and grounding pipeline.
- To debug issues and ensure system reliability.
- To comply with applicable law or valid legal process.

We do not sell your personal information or use it for advertising.

## Data Retention and Storage

- Retention periods depend on the deployment. Operators may configure databases and logs with their own retention policies.
- For self-hosted or local runs, data remains under your control.

## Security

We use industry-standard practices to protect data (e.g., encryption in transit, access controls). No system is completely secure; use the service in line with your organization’s data and compliance requirements.

## Third-Party Services

The pipeline may call external services (e.g., Google AI/Vertex AI for Gemini and MedGemma, UMLS for terminology). Their privacy policies apply to data sent to those services. See their respective documentation for details.

## Your Rights

Depending on your jurisdiction and the instance you use, you may have rights to access, correct, or delete your data. Contact the operator of the GemmaCrit instance you use, or open an issue in this repository for project-related privacy questions.

## Changes

We may update this policy from time to time. The “Last updated” date at the top will be revised when we do. Continued use of the service after changes constitutes acceptance of the updated policy.

## Contact

For privacy questions about this project, open an issue in the [repository](https://github.com/ElixirTrials/medgemma-hackathon) or contact the maintainers listed in the README.
