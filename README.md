# RECON_X — Reconnaissance Automation Tool

<p align="center">   <strong>A Local Web Interface for Automated Security Reconnaissance</strong> </p>

<p align="center">   <img src="https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">   <img src="https://img.shields.io/badge/Framework-Flask-black?style=for-the-badge&logo=flask&logoColor=white" alt="Flask">   <img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="MIT License"> </p>

RECON_X is a Flask-based web application that automates reconnaissance workflows for authorized bug bounty programs and penetration testing.

## Features

* Web-based interface with a cybersecurity terminal theme.
* Configurable reconnaissance workflow using `pipeline.json`.
* Subdomain enumeration and live-host discovery.
* URL collection, categorization, and parameter discovery.
* JavaScript and potential-secret scanning.
* Infrastructure reconnaissance and OSINT tasks.
* Port discovery and directory fuzzing.
* Configurable tool options and input files.
* Live logs, run continuation, and process stopping.
* Result organization, deduplication, and HTML summary reports.

Available features depend on the workflow configuration and installed tools.

## Workflow

```text
Subdomain Enumeration
        ↓
Merge & Deduplicate
        ↓
Live Host Discovery
        ↓
URL Discovery & Categorization
        ↓
JavaScript & Secret Scanning
        ↓
Infrastructure & OSINT
        ↓
Port Discovery & Directory Fuzzing
        ↓
Parameter Discovery & Vulnerability Scanning
        ↓
Results & Reports
```

## Requirements

* Python 3
* Dependencies listed in `requirements.txt`
* External CLI tools required by the selected steps in `pipeline.json`

## Installation

```bash
git clone https://github.com/islammahmoudfarouk-sketch/recon-tool.git
cd recon-tool

python3 -m venv .venv
source .venv/bin/activate

python -m pip install -r requirements.txt
python app.py
```

Open [**http://127.0.0.1:5000**](http://127.0.0.1:5000) in your browser.

## Usage

1. Enter the target and configure any required options.
2. Check tool availability and install missing dependencies as needed.
3. Select the reconnaissance steps you want to run.
4. Configure supported input files and command options.
5. Start the workflow and monitor live logs.
6. Review, merge, and deduplicate results or open the HTML report.

## Configuration

Edit `pipeline.json` to review or customize workflow steps, commands, inputs, outputs, and supported flags.

Some integrations may require API keys or tokens. Never commit credentials or sensitive reconnaissance results.

## Security Notice

* Use this tool only on systems you own or are explicitly authorized to test.
* RECON_X executes external commands configured in its workflow.
* Some steps, including vulnerability scanning, port discovery, and directory fuzzing, perform active testing.
* Keep the application bound to `127.0.0.1`; do not expose it publicly without appropriate security controls.
* Potential-secret matches and automated scan results require manual validation.

## License

Distributed under the [MIT License](LICENSE).

## Author

**Eng. Islam Mahmoud**

GitHub: [@islammahmoudfarouk-sketch](https://github.com/islammahmoudfarouk-sketch)
