# AFR AI Reviewer: Automated Federal Financial Compliance Engine

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991.svg)
![Azure](https://img.shields.io/badge/Azure-Document_Intelligence-0078D4.svg)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B.svg)

## Overview
Bridging the gap between complex financial reporting and artificial intelligence, the **AFR AI Reviewer** is an agentic workflow designed to automate the highly tedious presentation and disclosure review of Agency Financial Reports (AFRs). 

By combining technical accounting expertise with modern data engineering and AI orchestration, this pipeline reduces a multi-day manual ticking-and-tying process into a streamlined, interactive dashboard. This automation allows strategic finance, data, and reporting teams to shift their focus from formatting checklists to high-value financial analysis and anomaly detection.

*(📸 Insert a screenshot or GIF of your Streamlit Dashboard here once it's finished!)*

## The Business Impact
* **Accelerated Workflows:** Replaces 40+ hours of manual document review with a targeted AI evaluation engine.
* **Risk Mitigation:** Programmatic guardrails prevent AI hallucination, ensuring regulatory compliance data is strictly verified against source text.
* **Data Unification:** Seamlessly converts unstructured PDF reporting data into actionable, queryable formats.

## Key Features & Architecture

This project is built on a multi-stage data pipeline:

1. **Intelligent Document Ingestion:** Extracts unstructured text and tabular data from 120+ page draft AFR PDFs, converting them into highly readable Markdown while preserving structural integrity.
2. **Tri-State AI Evaluation Engine:** Executes a targeted, section-by-section analysis of the draft AFR. To prevent AI hallucination on off-document requirements (e.g., wet signatures, submission deadlines), the evaluation prompt is strictly constrained to a Tri-State output:
   * 🟢 **Met (Yes):** Requirement is explicitly satisfied.
   * 🔴 **Not Met (No):** Requirement is missing or incomplete.
   * 🟡 **Unverifiable (Manual Review):** Administrative/Formatting requirements securely flagged for human verification.
3. **Interactive UI:** A fully functional web application featuring drag-and-drop file ingestion, dynamic progress tracking, and an interactive data grid for filtering compliance anomalies.

## 🔒 Security & Intellectual Property Notice
*This is a Public Showcase repository.* To protect proprietary data structures and adhere to strict security best practices, the comprehensive regulatory databases, raw extraction files, and backend environment configurations have been intentionally omitted. 

This repository contains the core architectural scripts and a micro-batch test suite to demonstrate the agentic logic and pipeline orchestration without exposing the underlying intellectual property.

## Disclaimer
*This tool is a beta development project designed to accelerate financial operations and data review processes. It does not replace professional judgment. The final responsibility for ensuring regulatory compliance rests solely with the preparer and the reviewer.*

---
**Let's Connect:** If you are interested in discussing AI implementation in corporate finance, data strategy, or automation workflows, feel free to reach out via https://www.linkedin.com/in/seo-chang/ or seo.w.chang@gmail.com.
