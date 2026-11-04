# Quiklee Sales Intelligence

**An automated D2C company discovery, business research, lead qualification, and contact enrichment platform.**

## Overview

Quiklee Sales Intelligence is a Python-based automation platform designed to streamline the process of identifying and evaluating potential D2C brands and e-commerce businesses in India.

The system aims to reduce manual prospect research by automating company discovery, website data extraction, business research, lead qualification, contact enrichment, and Google Sheets integration.

It helps identify businesses that could be potential customers for Quiklee's shipping and logistics services.

## Business Objectives

- Discover emerging and established D2C brands across India.
- Automatically extract company information from websites.
- Research funding, business developments, and growth indicators.
- Analyze website traffic and estimate business potential.
- Qualify leads using a weighted scoring framework.
- Identify relevant decision-makers and business contacts.
- Maintain a centralized database and prevent duplicate research.
- Integrate qualified leads with Google Sheets.

## System Architecture

The platform follows a modular, pipeline-based architecture.

```text
                 COMPANY DISCOVERY
                        |
                        v
                  BRAVE SEARCH
                        |
                        v
                COMPANY EXTRACTION
                        |
                        v
                COMPANY VALIDATION
                        |
                        v
                DEDUPLICATION
                        |
                        v
                COMPANY DATABASE
                        |
                        v
                 BUSINESS RESEARCH
                 /      |       \
                /       |        \
          WEBSITE    FUNDING    TRAFFIC
          RESEARCH   RESEARCH   ANALYSIS
                \       |        /
                 \      |       /
                        v
                BUSINESS METRICS
                        |
                        v
                 LEAD QUALIFICATION
                        |
                        v
                 CONTACT ENRICHMENT
                        |
                        v
                 GOOGLE SHEETS
```

## Core Modules

| Module | Responsibility |
|---|---|
| Company Discovery | Discovers potential D2C companies using search sources. |
| Company Extraction | Extracts company names, domains, URLs, and descriptions. |
| Company Validation | Checks website accessibility and preliminary business indicators. |
| Deduplication | Identifies duplicate companies using domain and name matching. |
| Website Research | Extracts website metadata, products, prices, and social links. |
| Funding Research | Searches for funding, expansion, and business developments. |
| Traffic Analysis | Provides the integration foundation for website traffic research. |
| Business Metrics | Calculates estimated orders and revenue using explicit assumptions. |
| Lead Scoring | Evaluates companies using a weighted qualification framework. |
| Contact Enrichment | Identifies companies requiring decision-maker enrichment. |
| Lusha Integration | Provides the integration foundation for contact discovery. |
| Google Sheets | Provides the integration foundation for exporting company records. |

## Lead Qualification Framework

Companies are evaluated using six weighted criteria.

| Qualification Criteria | Weight |
|---|---:|
| Shipping Potential | 25% |
| Average Order Value (AOV) | 20% |
| COD Potential | 20% |
| Business Growth | 15% |
| E-commerce Relevance | 10% |
| Company Scale | 10% |
| **Total** | **100%** |

The scoring engine produces:

- Qualification score (out of 100).
- Lead category.
- Data completeness.
- Weighted scoring based on available inputs.

*Note: The initial weights are provisional and can be adjusted based on business requirements.*

## Business Metrics and Estimation

The platform distinguishes between verified information and estimates.

Examples include:

- Website traffic.
- Estimated monthly orders.
- Estimated monthly revenue.
- Average Order Value (AOV).
- COD potential.

Estimated orders are calculated using:

`Estimated Orders = Monthly Website Visits × Assumed Conversion Rate`

Estimated revenue:

`Estimated Revenue = Estimated Orders × Average Order Value`

All assumptions and estimates should be treated separately from verified business data. COD availability alone is not considered evidence of COD order share.

## Technology Stack

**Programming Language:** Python

**Data Processing:** Pandas, NumPy

**Web Research:** Brave Search API, Requests, BeautifulSoup

**Database:** SQLite

**Business Intelligence:** Business metrics and lead-scoring algorithms

**Traffic Research:** Similarweb API integration foundation

**Contact Enrichment:** Lusha integration foundation

**AI Integration:** Groq API (planned/optional)

**Google Integration:** Google Sheets API

**Development Environment:** VS Code, Git, GitHub

## Project Structure

```text
Quiklee_Sales_Intelligence/
│
├── config/
│   ├── __init__.py
│   └── settings.py
│
├── database/
│   ├── db.py
│   ├── company_repository.py
│   ├── contact_repository.py
│   └── research_repository.py
│
├── discovery/
│   ├── __init__.py
│   ├── brave_search.py
│   ├── source_discovery.py
│   ├── company_extractor.py
│   ├── company_validator.py
│   ├── deduplication.py
│   └── discovery_scheduler.py
│
├── research/
│   ├── __init__.py
│   ├── website_research.py
│   ├── funding_research.py
│   ├── traffic_analysis.py
│   ├── business_metrics.py
│   └── research_pipeline.py
│
├── qualification/
│   ├── lead_scoring.py
│   └── qualification_pipeline.py
│
├── enrichment/
│   ├── contact_enrichment.py
│   └── lusha_integration.py
│
├── integrations/
│   └── google_sheets.py
│
├── main.py
├── requirements.txt
├── .env
└── .gitignore
```

## Installation and Setup

### 1. Clone the Repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd Quiklee-Sales-Intelligence
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
```

Activate it on Windows:

```powershell
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root.

```env
BRAVE_API_KEY=your_brave_api_key
LUSHA_API_KEY=your_lusha_api_key
SIMILARWEB_API_KEY=your_similarweb_api_key

GOOGLE_SHEET_ID=your_google_sheet_id
GOOGLE_SERVICE_ACCOUNT_FILE=config/google_credentials.json
```

Add valid API credentials before enabling the corresponding integrations.

### 5. Run the Application

```bash
python main.py
```

The main execution pipeline initializes the database, starts company discovery, and initiates research for promising candidates.

## Database

The platform uses SQLite for persistent storage.

The database maintains:

- Company information.
- Research history.
- Company events.
- Enriched business contacts.
- Qualification scores.
- Research and enrichment statuses.

Duplicate detection helps prevent unnecessary repeat research and contact enrichment.

## Data Reliability

The system distinguishes between:

- **Verified:** Supported by a reliable source.
- **Estimated:** Calculated using documented assumptions.
- **Unknown:** Information not currently available.

Business potential and evidence confidence are treated as separate considerations to avoid qualifying companies solely on incomplete information.

## Integration Status

| Integration | Status |
|---|---|
| SQLite Database | Implemented |
| Company Discovery | Implemented; requires Brave API credentials |
| Company Extraction | Implemented |
| Company Validation | Implemented |
| Deduplication | Implemented |
| Website Research | Implemented |
| Funding Research | Implemented; requires Brave API credentials |
| Business Metrics | Implemented |
| Lead Scoring | Implemented |
| Research Pipeline | Implemented |
| Contact Repository | Implemented |
| Lusha API | Pending API documentation and access verification |
| Similarweb API | Pending API access and endpoint verification |
| Google Sheets | Integration scaffold; credentials required |
| Automated End-to-End Qualification | Further development required |

## Future Enhancements

- Improve automated business metric extraction.
- Integrate verified Similarweb traffic data.
- Complete Lusha contact enrichment.
- Automate evidence-based lead scoring.
- Integrate qualified leads with the existing Quiklee Google Sheets workflow.
- Improve company matching and duplicate detection.
- Add research confidence and source verification mechanisms.

## Project Purpose

The ultimate goal is to transform manual D2C prospect research into a structured, repeatable, and scalable sales intelligence workflow that helps Quiklee identify high-potential businesses and prioritize sales outreach.

---

**Project:** Quiklee Sales Intelligence  
**Language:** Python  
**Database:** SQLite  
**Domain:** Sales Intelligence | D2C Research | Lead Generation | Business Analytics