# Agency Financial Report (AFR) AI Agent: Disclosure & Compliance Auditor

### Bridging the gap between Federal Financial Reporting and Agentic AI.

As a CPA and AI solution associate, I built this agentic workflow to solve one of the most tedious tasks in federal financial reporting: manually reviewing Agency Financial Reports (AFR) against thousands of pages of authoritative guidance (OMB A-136 & SFFAS).

---

## How It Works
This project utilizes a **Two-Agent System** powered by **OpenAI's Reasoning Models**:
1. **The Compliance Architect:** Scans the latest SFFAS Handbook and OMB A-136 to generate a dynamic disclosure checklist.
2. **The Auditor Agent:** Ingests a draft AFR (via Azure AI Document Intelligence) and flags missing or non-compliant disclosures against the checklist using Chain-of-Thought reasoning.

## Tech Stack
* **Language:** Python 3.11+
* **Reasoning Engine:** OpenAI (o1-preview / GPT-4o)
* **Document Extraction:** Azure AI Document Intelligence (Advanced OCR for financial tables)
* **Framework:** Streamlit (Frontend) & LangChain

---

## Disclaimer & User Responsibility
* **Experimental Prototype:** These agents are AI-driven and subject to "hallucinations." They should be used as a high-level review tool, not a final audit sign-off.
* **The Human-in-the-Loop:** Per professional standards, the **user is the ultimate responsible party** for verifying all AI-generated findings against authoritative sources.

---

## Feedback & Collaboration
I am building this in the open. If you are a federal finance professional or an AI engineer, I'd love your feedback!
**Contact:** https://www.linkedin.com/in/seo-chang/ or seo.w.chang@gmail.com
Agentic AI workflow for automating Federal Disclosure Checklist generation and AFR compliance reviews (OMB A-136 &amp; SFFAS)
